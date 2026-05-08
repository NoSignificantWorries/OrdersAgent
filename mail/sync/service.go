package sync

import (
    "context"
    "log"

    "OrdersAgent/mail/client"
    "OrdersAgent/mail/orders"
    "OrdersAgent/mail/parser"
)

type Service struct {
    processor *orders.Processor
}

func New(processor *orders.Processor) *Service {
    return &Service{processor: processor}
}

// SyncMailboxOnce выполняет один проход по unread письмам через уже открытый IMAP-клиент
func (s *Service) SyncMailboxOnce(ctx context.Context, imap *client.Client) error {
    uids, err := imap.FetchUnread()
    if err != nil {
        log.Printf("fetch unread: %v", err)
        return err
    }

    if len(uids) == 0 {
        return nil
    }

    log.Printf("found %d unread emails", len(uids))

    for _, uid := range uids {
        if err := ctx.Err(); err != nil {
            return err
        }

        fetchCmd, err := imap.FetchMessage(uid)
        if err != nil {
            log.Printf("fetch message uid=%d: %v", uid, err)
            continue
        }

        email, err := parser.ParseMessage(uid, fetchCmd)
		if closeErr := fetchCmd.Close(); closeErr != nil {
			log.Printf("close fetch uid=%d: %v", uid, closeErr)
		}
		if err != nil {
			log.Printf("parse uid=%d: %v", uid, err)
			continue
		}

        if err := ctx.Err(); err != nil {
            return err
        }

        if err := s.processor.ProcessEmail(email); err != nil {
            log.Printf("process uid=%d: %v", uid, err)
            continue
        }

        if err := imap.MarkRead(uid); err != nil {
            log.Printf("mark read uid=%d: %v", uid, err)
        }
    }

    return nil
}