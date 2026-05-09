package main

import (
	"log"
	"os"
	"time"

	"OrdersAgent/mail/internal/client"
	"OrdersAgent/mail/internal/config"
	"OrdersAgent/mail/internal/orders"
	"OrdersAgent/mail/internal/parser"
	"OrdersAgent/mail/internal/storage"

	"OrdersAgent/storage/api"
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
		log.Printf("get user mail auth | user_id=%d err=%v", userID, err)
		return
	}

	if mailAuth.AccessToken == "" {
		log.Printf("empty mail access token | user_id=%d", userID)
		return
	}

	// Обновляем access_token, если он скоро истечёт
	if time.Now().After(mailAuth.AccessExpiresAt.Add(-1 * time.Minute)) {
		log.Printf("access token expired or about to expire, refreshing | user_id=%d", userID)

		newToken, err := client.RefreshYandexToken(
			os.Getenv("YANDEX_TOKEN_URL"),
			os.Getenv("YANDEX_CLIENT_ID"),
			os.Getenv("YANDEX_CLIENT_SECRET"),
			mailAuth.RefreshToken,
		)
		if err != nil {
			log.Printf("refresh token | user_id=%d err=%v", userID, err)
			return
		}

		mailAuth.AccessToken = newToken.AccessToken
		mailAuth.RefreshToken = newToken.RefreshToken
		mailAuth.AccessExpiresAt = newToken.AccessExpiresAt

		if err := storage.UpdateUserMailTokens(db, userID, mailAuth); err != nil {
			log.Printf("update mail tokens | user_id=%d err=%v", userID, err)
			return
		}

		log.Printf("access token refreshed | user_id=%d", userID)
	}

	// IMAP‑клиент по OAuth/XOAUTH2
	imapClient, err := client.NewOAuth(cfg, mailAuth.Email, mailAuth.AccessToken)
	if err != nil {
		log.Printf("IMAP client | user_id=%d err=%v", userID, err)
		return
	}
	defer imapClient.Close()

	processor := orders.New(repo, userID)

	// Периодический обход писем
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	// Первый проход сразу
	ProcessEmails(imapClient, stopChan, processor)

	for {
		select {
		case <-ticker.C:
			ProcessEmails(imapClient, stopChan, processor)
		case <-stopChan:
			log.Printf("user worker stopped | user_id=%d", userID)
			return
		}
	}
}

// Обработка всех непрочитанных писем.
func ProcessEmails(imap *client.Client, stopChan <-chan struct{}, processor *orders.Processor) {
	uids, err := imap.FetchUnread()
	if err != nil {
		log.Printf("fetch unread: %v", err)
		return
	}

	if len(uids) == 0 {
		return
	}

	log.Printf("found %d unread emails", len(uids))

	for _, uid := range uids {
		select {
		case <-stopChan:
			log.Printf("interrupt while processing, stopping")
			return
		default:
		}

		fetchCmd, err := imap.FetchMessage(uid)
		if err != nil {
			log.Printf("fetch message uid=%d: %v", uid, err)
			continue
		}

		email, err := parser.ParseMessage(uid, fetchCmd)
		if err != nil {
			log.Printf("parse uid=%d: %v", uid, err)
			fetchCmd.Close()
			continue
		}

		if err := processor.ProcessEmail(email); err != nil {
			log.Printf("process uid=%d: %v", uid, err)
		}

		fetchCmd.Close()

		if err := imap.MarkRead(uid); err != nil {
			log.Printf("mark read uid=%d: %v", uid, err)
		}
	}
}