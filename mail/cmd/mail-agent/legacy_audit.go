package main

import (
	"context"
	"encoding/csv"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/emersion/go-imap/v2"

	"mail/internal/client"
	"mail/internal/config"
	"mail/internal/storage"
	"mail/storage/api"
)

type legacyAuditEmail struct {
	ID        int64
	UID       int64
	MessageID string
	Subject   string
	From      string
}

func normalizeLegacyMessageID(value string) string {
	value = strings.TrimSpace(value)

	if strings.HasPrefix(value, "<") &&
		strings.HasSuffix(value, ">") {
		value = strings.TrimSpace(value[1 : len(value)-1])
	}

	return value
}

func legacyAuditAddresses(addresses []imap.Address) string {
	values := make([]string, 0, len(addresses))

	for _, address := range addresses {
		values = append(
			values,
			address.Mailbox+"@"+address.Host,
		)
	}

	return strings.Join(values, "; ")
}

func runLegacyAudit(
	db *api.DB,
	cfg *config.Config,
	userID int64,
) error {
	mailAuth, err := storage.GetUserMailAuth(db, userID)
	if err != nil {
		return fmt.Errorf("get mail auth: %w", err)
	}

	if mailAuth.AccessToken == "" {
		return fmt.Errorf("empty access token for user_id=%d", userID)
	}

	if !time.Now().Before(
		mailAuth.AccessExpiresAt.Add(-time.Minute),
	) {
		return fmt.Errorf(
			"access token expired or about to expire; audit does not refresh tokens",
		)
	}

	rows, err := db.Conn.QueryContext(
		context.Background(),
		`
            SELECT
                id,
                email_uid,
                COALESCE(message_id, ''),
                COALESCE(email_subject, ''),
                COALESCE(email_from, '')
            FROM emails
            WHERE mailbox = $1
              AND uid_validity IS NULL
            ORDER BY email_uid, id
        `,
		mailAuth.Email,
	)
	if err != nil {
		return fmt.Errorf("query legacy emails: %w", err)
	}

	var emails []legacyAuditEmail

	for rows.Next() {
		var email legacyAuditEmail

		if err := rows.Scan(
			&email.ID,
			&email.UID,
			&email.MessageID,
			&email.Subject,
			&email.From,
		); err != nil {
			_ = rows.Close()
			return fmt.Errorf("scan legacy email: %w", err)
		}

		emails = append(emails, email)
	}

	rowsErr := rows.Err()
	closeErr := rows.Close()

	if rowsErr != nil {
		return fmt.Errorf("read legacy emails: %w", rowsErr)
	}
	if closeErr != nil {
		return fmt.Errorf("close legacy rows: %w", closeErr)
	}

	c, err := client.NewOAuth(
		cfg,
		mailAuth.Email,
		mailAuth.AccessToken,
	)
	if err != nil {
		return fmt.Errorf("connect IMAP: %w", err)
	}
	defer c.Close()

	uidValidity, _, err := c.InboxSyncBoundary()
	if err != nil {
		return fmt.Errorf("initial boundary: %w", err)
	}

	records := [][]string{
		{
			"email_id",
			"mailbox",
			"uid",
			"observed_uid_validity",
			"status",
			"db_message_id",
			"server_message_id",
			"db_subject",
			"server_subject",
			"db_from",
			"server_from",
			"server_date",
		},
	}

	counts := make(map[string]int)

	for _, email := range emails {
		if email.UID <= 0 || email.UID > 4294967295 {
			return fmt.Errorf(
				"invalid legacy UID: email_id=%d uid=%d",
				email.ID,
				email.UID,
			)
		}

		envelope, found, err := c.FetchLegacyEnvelope(
			imap.UID(email.UID),
		)
		if err != nil {
			return fmt.Errorf(
				"audit stopped at email_id=%d uid=%d: %w",
				email.ID,
				email.UID,
				err,
			)
		}

		status := "missing_on_server"
		serverMessageID := ""
		serverSubject := ""
		serverFrom := ""
		serverDate := ""

		if found {
			serverMessageID = envelope.MessageID
			serverSubject = envelope.Subject
			serverFrom = legacyAuditAddresses(envelope.From)

			if !envelope.Date.IsZero() {
				serverDate = envelope.Date.Format(time.RFC3339)
			}

			dbID := normalizeLegacyMessageID(email.MessageID)
			serverID := normalizeLegacyMessageID(serverMessageID)

			switch {
			case dbID == "":
				status = "missing_db_message_id"
			case serverID == "":
				status = "missing_server_message_id"
			case dbID == serverID:
				status = "candidate_match"
			default:
				status = "message_id_mismatch"
			}
		}

		records = append(records, []string{
			strconv.FormatInt(email.ID, 10),
			mailAuth.Email,
			strconv.FormatInt(email.UID, 10),
			strconv.FormatUint(uint64(uidValidity), 10),
			status,
			email.MessageID,
			serverMessageID,
			email.Subject,
			serverSubject,
			email.From,
			serverFrom,
			serverDate,
		})

		counts[status]++
	}

	finalValidity, _, err := c.InboxSyncBoundary()
	if err != nil {
		return fmt.Errorf("final boundary: %w", err)
	}

	if finalValidity != uidValidity {
		return fmt.Errorf(
			"UIDVALIDITY changed: initial=%d final=%d; report rejected",
			uidValidity,
			finalValidity,
		)
	}

	outputPath := os.Getenv("MAIL_LEGACY_AUDIT_OUTPUT")
	if outputPath == "" {
		outputPath = "/tmp/legacy-audit.csv"
	}

	file, err := os.Create(outputPath)
	if err != nil {
		return fmt.Errorf("create report: %w", err)
	}

	writer := csv.NewWriter(file)
	writeErr := writer.WriteAll(records)
	fileCloseErr := file.Close()

	if writeErr != nil {
		return fmt.Errorf("write report: %w", writeErr)
	}
	if fileCloseErr != nil {
		return fmt.Errorf("close report: %w", fileCloseErr)
	}

	log.Printf(
		"legacy audit complete | user_id=%d mailbox=%s uid_validity=%d total=%d candidate_match=%d message_id_mismatch=%d missing_on_server=%d missing_server_message_id=%d missing_db_message_id=%d output=%s",
		userID,
		mailAuth.Email,
		uidValidity,
		len(emails),
		counts["candidate_match"],
		counts["message_id_mismatch"],
		counts["missing_on_server"],
		counts["missing_server_message_id"],
		counts["missing_db_message_id"],
		outputPath,
	)

	return nil
}
