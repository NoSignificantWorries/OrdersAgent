package main

import (
	"errors"
	"io"
	"log"
	"net"
	"os"
	"strings"
	"syscall"
	"time"

	"mail/internal/client"
	"mail/internal/config"
	"mail/internal/orders"
	"mail/internal/parser"
	"mail/internal/storage"

	"mail/storage/api"
)

// Воркер для одного пользователя: управляет токенами, IMAP-клиентом и обработкой писем.
func runUserWorker(
	userID int64,
	db *api.DB,
	cfg *config.Config,
	repo storage.Repository,
	stopChan <-chan struct{},
	onExit func(userID int64),
) {
	log.Printf("user worker started | user_id=%d", userID)
	defer onExit(userID)

	mailAuth, err := storage.GetUserMailAuth(db, userID)
    if err != nil {
        log.Printf("get user mail auth: %v", err)
        return
    }
    userEmail := mailAuth.Email

	processor := orders.New(repo, userID)

	var imapClient *client.Client
	defer func() {
		if imapClient != nil {
			imapClient.Close()
		}
	}()

	getConnectedClient := func() (*client.Client, error) {
		if imapClient != nil {
			return imapClient, nil
		}

		mailAuth, err := storage.GetUserMailAuth(db, userID)
		if err != nil {
			return nil, err
		}

		if mailAuth.AccessToken == "" {
			return nil, errors.New("empty mail access token")
		}

		if time.Now().After(mailAuth.AccessExpiresAt.Add(-1 * time.Minute)) {
			log.Printf("access token expired or about to expire, refreshing | user_id=%d", userID)

			newToken, err := client.RefreshYandexToken(
				os.Getenv("YANDEX_TOKEN_URL"),
				os.Getenv("YANDEX_CLIENT_ID"),
				os.Getenv("YANDEX_CLIENT_SECRET"),
				mailAuth.RefreshToken,
			)
			if err != nil {
				return nil, err
			}

			mailAuth.AccessToken = newToken.AccessToken
			mailAuth.RefreshToken = newToken.RefreshToken
			mailAuth.AccessExpiresAt = newToken.AccessExpiresAt

			if err := storage.UpdateUserMailTokens(db, userID, mailAuth); err != nil {
				return nil, err
			}

			log.Printf("access token refreshed | user_id=%d", userID)
		}

		c, err := client.NewOAuth(cfg, mailAuth.Email, mailAuth.AccessToken)
		if err != nil {
			return nil, err
		}

		log.Printf("IMAP client connected | user_id=%d", userID)
		imapClient = c
		return imapClient, nil
	}

	resetClient := func(reason error) {
		if reason != nil {
			log.Printf("reset IMAP client | user_id=%d err=%v", userID, reason)
		}
		if imapClient != nil {
			imapClient.Close()
			imapClient = nil
		}
	}

	processOnce := func() {
		c, err := getConnectedClient()
		if err != nil {
			log.Printf("get IMAP client | user_id=%d err=%v", userID, err)
			return
		}

		err = ProcessEmails(c, stopChan, processor, userEmail)
		if err == nil {
			return
		}

		log.Printf("process emails | user_id=%d err=%v", userID, err)

		if isReconnectableError(err) {
			resetClient(err)

			select {
			case <-stopChan:
				return
			case <-time.After(5 * time.Second):
			}
			return
		}
	}

	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	processOnce()

	for {
		select {
		case <-ticker.C:
			processOnce()
		case <-stopChan:
			log.Printf("user worker stopped | user_id=%d", userID)
			return
		}
	}
}

func ProcessEmails(imap *client.Client, stopChan <-chan struct{}, processor *orders.Processor, userEmail string) error {
    uids, err := imap.FetchUnread()
    if err != nil {
        return err
    }

    log.Printf("ProcessEmails | unread_count=%d uids=%v", len(uids), uids)

    if len(uids) == 0 {
        return nil
    }

    for _, uid := range uids {
        log.Printf("ProcessEmails | start uid=%d", uid)

        select {
        case <-stopChan:
            log.Printf("interrupt while processing, stopping")
            return nil
        default:
        }

        fetchCmd, err := imap.FetchMessage(uid)
        if err != nil {
            log.Printf("fetch message uid=%d: %v", uid, err)
            if isReconnectableError(err) {
                return err
            }
            continue
        }

        log.Printf("ProcessEmails | fetched uid=%d", uid)

        email, err := parser.ParseMessage(uid, fetchCmd, userEmail)
        if err != nil {
            log.Printf("parse uid=%d: %v", uid, err)
            fetchCmd.Close()
            continue
        }

        log.Printf("ProcessEmails | parsed uid=%d subject=%q from=%q attachments=%d",
            uid, email.Subject, email.From, len(email.Files))

        if err := processor.ProcessEmail(*email); err != nil {
            log.Printf("process uid=%d: %v", uid, err)
        } else {
            log.Printf("ProcessEmails | processed uid=%d", uid)
        }

        fetchCmd.Close()

        if err := imap.MarkRead(uid); err != nil {
            log.Printf("mark read uid=%d: %v", uid, err)
            if isReconnectableError(err) {
                return err
            }
        } else {
            log.Printf("ProcessEmails | marked read uid=%d", uid)
        }
    }

    return nil
}

func isReconnectableError(err error) bool {
	if err == nil {
		return false
	}

	msg := strings.ToLower(err.Error())

	if strings.Contains(msg, "use of closed network connection") ||
		strings.Contains(msg, "connection reset by peer") ||
		strings.Contains(msg, "broken pipe") ||
		strings.Contains(msg, "unexpected eof") ||
		strings.Contains(msg, "eof") ||
		strings.Contains(msg, "i/o timeout") ||
		strings.Contains(msg, "connection refused") {
		return true
	}

	if errors.Is(err, io.EOF) ||
		errors.Is(err, net.ErrClosed) ||
		errors.Is(err, syscall.EPIPE) ||
		errors.Is(err, syscall.ECONNRESET) {
		return true
	}

	var netErr net.Error
	if errors.As(err, &netErr) && netErr.Timeout() {
		return true
	}

	return false
}