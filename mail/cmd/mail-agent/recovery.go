package main

import (
	"context"
	"fmt"
	"log"

	"github.com/emersion/go-imap/v2"

	"mail/internal/client"
	"mail/internal/orders"
	"mail/internal/parser"
	"mail/storage/api"
)

const recoveryUIDWindow int64 = 500

// recoverInboxBatch проверяет один участок UID.
// done=true означает, что достигнута граница, полученная в этом вызове.
// Флаги прочтения здесь не изменяются.
func recoverInboxBatch(
	ctx context.Context,
	userID int64,
	db *api.DB,
	c *client.Client,
	processor *orders.Processor,
	stopChan <-chan struct{},
) (done bool, err error) {
	select {
	case <-stopChan:
		return false, nil
	default:
	}

	// Начальную точку берём из снимка подключения.
	// Повторные вызовы не перезаписывают существующее состояние.
	initialUID := int64(c.UIDNextAtConnect()) - 1

	state, created, err := db.GetOrCreateMailSyncState(
		ctx,
		userID,
		c.UIDValidity(),
		initialUID,
	)
	if err != nil {
		return false, fmt.Errorf("prepare inbox recovery: %w", err)
	}

	if created {
		log.Printf(
			"mail sync state initialized | user_id=%d email=%s uid_validity=%d initial_uid=%d",
			userID,
			c.Email(),
			state.UIDValidity,
			state.LastReconciledUID,
		)
	}

	uidValidity, uidNext, err := c.InboxSyncBoundary()
	if err != nil {
		return false, err
	}

	if uidValidity != state.UIDValidity {
		return false, fmt.Errorf(
			"UIDVALIDITY mismatch during recovery: user_id=%d stored=%d server=%d",
			userID,
			state.UIDValidity,
			uidValidity,
		)
	}

	upperUID := int64(uidNext) - 1

	if upperUID < state.LastReconciledUID {
		return false, fmt.Errorf(
			"inbox recovery boundary moved backwards: user_id=%d checkpoint=%d upper_uid=%d",
			userID,
			state.LastReconciledUID,
			upperUID,
		)
	}

	if upperUID == state.LastReconciledUID {
		log.Printf(
			"inbox recovery caught up | user_id=%d email=%s uid_validity=%d checkpoint=%d",
			userID,
			c.Email(),
			state.UIDValidity,
			state.LastReconciledUID,
		)
		return true, nil
	}

	firstUID := state.LastReconciledUID + 1
	lastUID := state.LastReconciledUID + recoveryUIDWindow

	if lastUID > upperUID {
		lastUID = upperUID
	}

	uids, err := c.SearchUIDRange(
		imap.UID(firstUID),
		imap.UID(lastUID),
	)
	if err != nil {
		return false, err
	}

	for _, uid := range uids {
		select {
		case <-stopChan:
			return false, nil
		default:
		}

		fetchCmd, err := c.FetchMessage(uid)
		if err != nil {
			return false, fmt.Errorf(
				"recovery fetch uid=%d: %w",
				uid,
				err,
			)
		}

		email, err := parser.ParseMessage(uid, fetchCmd, c.Email())
		if err != nil {
			return false, fmt.Errorf(
				"recovery parse uid=%d: %w",
				uid,
				err,
			)
		}

		email.UIDValidity = c.UIDValidity()

		if err := processor.ProcessEmail(*email); err != nil {
			return false, fmt.Errorf(
				"recovery save uid=%d subject=%q: %w",
				uid,
				email.Subject,
				err,
			)
		}
	}

	// Не продвигаем точку, если за время обработки изменилась версия папки.
	finalValidity, _, err := c.InboxSyncBoundary()
	if err != nil {
		return false, err
	}

	if finalValidity != state.UIDValidity {
		return false, fmt.Errorf(
			"UIDVALIDITY changed before checkpoint update: user_id=%d stored=%d server=%d",
			userID,
			state.UIDValidity,
			finalValidity,
		)
	}

	select {
	case <-stopChan:
		return false, nil
	default:
	}

	if err := db.AdvanceMailSyncState(
		ctx,
		userID,
		state.UIDValidity,
		state.LastReconciledUID,
		lastUID,
	); err != nil {
		return false, err
	}

	log.Printf(
		"inbox recovery checkpoint advanced | user_id=%d email=%s uid_validity=%d previous_uid=%d checkpoint=%d found=%d upper_uid=%d",
		userID,
		c.Email(),
		state.UIDValidity,
		state.LastReconciledUID,
		lastUID,
		len(uids),
		upperUID,
	)

	return lastUID == upperUID, nil
}
