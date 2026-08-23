package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
	"strings"
	"net/mail"
	"crypto/rand"
	"encoding/hex"
    "bytes"
    "io"
    "encoding/base64"
    "html"
    "mime"
    "mime/multipart"
    "mime/quotedprintable"
    "regexp"

    mailsmtp "mail/internal/smtp"
	"mail/internal/parser"
	"mail/storage/api"
	minio "worker/minio/minio"
	"mail/internal/config"
)

// Repository — общий интерфейс хранилища.
type Repository interface {
	SaveOrder(userID int64, order any) error
	HasEmail(mailbox string, emailUID int64) (bool, error)
}

// UserMailAuth — OAuth‑данные почты пользователя из таблицы users.
type UserMailAuth struct {
	Email           string
	AccessToken     string
	RefreshToken    string
	AccessExpiresAt time.Time
}

// MailUser — пользователь, у которого настроена почта.
type MailUser struct {
	ID    int64
	Email string
}

type EmailReplyContext struct {
    EmailID           int64
    UserID            int64
    Mailbox           string
    EmailFrom         string
    ReplyTo           string
    MessageID         string
    InReplyTo         string
    ReferencesHeader  string
    EmailSubject      string
    RawEmail          string
    EmailDate         time.Time
}

type ReplyAttachment struct {
    Filename    string
    ContentType string
    Data        []byte
}

// ReplyToEmailRequest — данные для ответа на письмо.
type ReplyToEmailRequest struct {
    EmailID     int64
    Body        string
    Attachments []ReplyAttachment
}

type SendAttachment struct {
    Filename    string
    ContentType string
    Data        []byte
}

type SendEmailRequest struct {
    Mailbox     string
    To          string
    Subject     string
    Body        string
    Attachments []SendAttachment
}

type ForwardAttachment struct {
	DocumentID  int64  `json:"document_id"`
	Filename    string `json:"filename"`
	ContentType string `json:"content_type"`
	SizeBytes   int64  `json:"size_bytes"`
	Selected    bool   `json:"selected"`
}

type ForwardDraft struct {
	EmailID     int64               `json:"email_id"`
	Mailbox     string              `json:"mailbox"`
	To          string              `json:"to"`
	Subject     string              `json:"subject"`
	Body        string              `json:"body"`
	Attachments []ForwardAttachment `json:"attachments"`
}

type ForwardEmailRequest struct {
	EmailID            int64
	To                 string
	Body               string
	IncludeDocumentIDs []int64
	Attachments        []SendAttachment
    SourceType          string
}

type ReplyDraft struct {
    EmailID int64  `json:"email_id"`
    Mailbox string `json:"mailbox"`
    To      string `json:"to"`
    Subject string `json:"subject"`
    Body    string `json:"body"`
}

// DBRepo — пишет метаданные в Postgres и файлы в MinIO.
type DBRepo struct {
	db    *api.DB
	incomingStore  *minio.CloudStorage
	outgoingStore *minio.CloudStorage
}

type SentAttachment struct {
    Filename    string
    ContentType string
    Data        []byte
}

type SentDocumentRecord struct {
    ID             int64
    SentEmailID     int64
    Filename       string
    MinioObjectKey string
    ContentType    string
    SizeBytes      int64
}

func extractReplyAddress(replyTo string, emailFrom string) (string, error) {
    if strings.TrimSpace(replyTo) != "" {
        addr, err := mail.ParseAddress(strings.TrimSpace(replyTo))
        if err == nil {
            return addr.Address, nil
        }
        return strings.TrimSpace(replyTo), nil
    }

    if strings.TrimSpace(emailFrom) != "" {
        addr, err := mail.ParseAddress(strings.TrimSpace(emailFrom))
        if err != nil {
            return "", fmt.Errorf("parse EmailFrom address: %w", err)
        }
        return addr.Address, nil
    }

    return "", fmt.Errorf("both Reply-To and EmailFrom are empty")
}

func normalizeMessageID(v string) string {
    v = strings.TrimSpace(v)
    if v == "" {
        return ""
    }
    if strings.HasPrefix(v, "<") && strings.HasSuffix(v, ">") {
        return v
    }
    return "<" + v + ">"
}

func messageIDDomain(email string) string {
    email = strings.TrimSpace(strings.ToLower(email))
    parts := strings.Split(email, "@")
    if len(parts) == 2 && strings.TrimSpace(parts[1]) != "" {
        return strings.TrimSpace(parts[1])
    }
    return "localhost"
}

func generateMessageID(mailbox string, now time.Time) (string, error) {
    b := make([]byte, 12)
    if _, err := rand.Read(b); err != nil {
        return "", fmt.Errorf("generate message id entropy: %w", err)
    }

    domain := messageIDDomain(mailbox)
    token := hex.EncodeToString(b)

    return fmt.Sprintf("<%d.%s@%s>", now.UnixNano(), token, domain), nil
}

func parseRecipients(raw string) ([]string, error) {
    raw = strings.TrimSpace(raw)
    if raw == "" {
        return nil, fmt.Errorf("empty recipients")
    }

    parts := strings.FieldsFunc(raw, func(r rune) bool {
        return r == ',' || r == ';' || r == '\n'
    })

    recipients := make([]string, 0, len(parts))
    seen := make(map[string]struct{})

    for _, part := range parts {
        part = strings.TrimSpace(part)
        if part == "" {
            continue
        }

        addr, err := mail.ParseAddress(part)
        if err != nil {
            return nil, fmt.Errorf("invalid recipient %q: %w", part, err)
        }

        email := strings.TrimSpace(addr.Address)
        if email == "" {
            return nil, fmt.Errorf("empty recipient address")
        }

        key := strings.ToLower(email)
        if _, ok := seen[key]; ok {
            continue
        }
        seen[key] = struct{}{}
        recipients = append(recipients, email)
    }

    if len(recipients) == 0 {
        return nil, fmt.Errorf("no valid recipients")
    }

    return recipients, nil
}

func normalizeSourceType(v string) string {
    if strings.EqualFold(strings.TrimSpace(v), "sent") {
        return "sent"
    }
    return "inbox"
}

func ListSentDocumentsByEmailID(db *api.DB, emailID int64) ([]SentDocumentRecord, error) {
    rows, err := db.Conn.Query(`
        SELECT id, sent_email_id, filename, minio_object_key, content_type, size_bytes
        FROM sent_documents
        WHERE sent_email_id = $1
        ORDER BY id
    `, emailID)
    if err != nil {
        return nil, fmt.Errorf("query sent documents by email: %w", err)
    }
    defer rows.Close()

    var items []SentDocumentRecord
    for rows.Next() {
        var rec SentDocumentRecord
        if err := rows.Scan(
            &rec.ID,
            &rec.SentEmailID,
            &rec.Filename,
            &rec.MinioObjectKey,
            &rec.ContentType,
            &rec.SizeBytes,
        ); err != nil {
            return nil, fmt.Errorf("scan sent document: %w", err)
        }
        items = append(items, rec)
    }

    if err := rows.Err(); err != nil {
        return nil, fmt.Errorf("iterate sent documents: %w", err)
    }

    return items, nil
}

func ListSentDocumentsByIDsForEmail(db *api.DB, emailID int64, documentIDs []int64) ([]SentDocumentRecord, error) {
    if len(documentIDs) == 0 {
        return []SentDocumentRecord{}, nil
    }

    placeholders := make([]string, 0, len(documentIDs))
    args := make([]any, 0, len(documentIDs)+1)

    args = append(args, emailID) // $1

    for i, id := range documentIDs {
        placeholders = append(placeholders, fmt.Sprintf("$%d", i+2))
        args = append(args, id)
    }

    query := fmt.Sprintf(`
        SELECT id, sent_email_id, filename, minio_object_key, content_type, size_bytes
        FROM sent_documents
        WHERE sent_email_id = $1
          AND id IN (%s)
        ORDER BY id
    `, strings.Join(placeholders, ", "))

    rows, err := db.Conn.Query(query, args...)
    if err != nil {
        return nil, fmt.Errorf("query sent documents by ids: %w", err)
    }
    defer rows.Close()

    var items []SentDocumentRecord
    for rows.Next() {
        var rec SentDocumentRecord
        if err := rows.Scan(
            &rec.ID,
            &rec.SentEmailID,
            &rec.Filename,
            &rec.MinioObjectKey,
            &rec.ContentType,
            &rec.SizeBytes,
        ); err != nil {
            return nil, fmt.Errorf("scan sent document by ids: %w", err)
        }
        items = append(items, rec)
    }

    if err := rows.Err(); err != nil {
        return nil, fmt.Errorf("iterate sent documents by ids: %w", err)
    }

    return items, nil
}

func buildForwardSubject(subject string) string {
	subject = strings.TrimSpace(subject)
	if subject == "" {
		return "Fwd:"
	}
	if strings.HasPrefix(strings.ToLower(subject), "fwd:") {
		return subject
	}
	return "Fwd: " + subject
}

func buildReplySubject(subject string) string {
    subject = strings.TrimSpace(subject)
    if subject == "" {
        return "Re:"
    }
    if strings.HasPrefix(strings.ToLower(subject), "re:") {
        return subject
    }
    return "Re: " + subject
}

func normalizeEmailText(s string) string {
    s = strings.ReplaceAll(s, "\r\n", "\n")
    s = strings.ReplaceAll(s, "\r", "\n")
    s = html.UnescapeString(s)

    lines := strings.Split(s, "\n")
    cleaned := make([]string, 0, len(lines))
    emptyCount := 0

    for _, line := range lines {
        line = strings.TrimRight(line, " \t")
        if strings.TrimSpace(line) == "" {
            emptyCount++
            if emptyCount > 1 {
                continue
            }
            cleaned = append(cleaned, "")
            continue
        }
        emptyCount = 0
        cleaned = append(cleaned, line)
    }

    return strings.TrimSpace(strings.Join(cleaned, "\n"))
}

func stripHTMLToText(s string) string {
    if strings.TrimSpace(s) == "" {
        return ""
    }

    reBreaks := regexp.MustCompile(`(?is)<\s*(br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>`)
    s = reBreaks.ReplaceAllString(s, "\n")

    reBlocks := regexp.MustCompile(`(?is)</\s*(p|div|li|tr|table|section|article|ul|ol|h[1-6])\s*>`)
    s = reBlocks.ReplaceAllString(s, "\n")

    reTags := regexp.MustCompile(`(?is)<[^>]+>`)
    s = reTags.ReplaceAllString(s, "")

    return normalizeEmailText(s)
}

func decodePartBody(part *multipart.Part) ([]byte, error) {
    encoding := strings.ToLower(strings.TrimSpace(part.Header.Get("Content-Transfer-Encoding")))

    switch encoding {
    case "base64":
        data, err := io.ReadAll(base64.NewDecoder(base64.StdEncoding, part))
        if err == nil {
            return data, nil
        }

        rawData, rawErr := io.ReadAll(part)
        if rawErr != nil {
            return nil, rawErr
        }

        compact := strings.Map(func(r rune) rune {
            switch r {
            case '\r', '\n', '\t', ' ':
                return -1
            default:
                return r
            }
        }, string(rawData))

        decoded, decErr := base64.StdEncoding.DecodeString(compact)
        if decErr != nil {
            return nil, decErr
        }
        return decoded, nil

    case "quoted-printable":
        return io.ReadAll(quotedprintable.NewReader(part))

    default:
        return io.ReadAll(part)
    }
}

func extractPreferredTextFromMultipartReader(mr *multipart.Reader) (plain string, htmlText string, err error) {
    for {
        part, err := mr.NextPart()
        if err == io.EOF {
            return plain, htmlText, nil
        }
        if err != nil {
            return plain, htmlText, err
        }

        dispType, _, _ := mime.ParseMediaType(part.Header.Get("Content-Disposition"))
        if strings.EqualFold(dispType, "attachment") {
            continue
        }

        contentType := part.Header.Get("Content-Type")
        mediaType, params, parseErr := mime.ParseMediaType(contentType)
        if parseErr != nil || mediaType == "" {
            mediaType = "text/plain"
        }
        mediaType = strings.ToLower(strings.TrimSpace(mediaType))

        if strings.HasPrefix(mediaType, "multipart/") {
            boundary := params["boundary"]
            if strings.TrimSpace(boundary) == "" {
                continue
            }

            nestedPlain, nestedHTML, nestedErr := extractPreferredTextFromMultipartReader(
                multipart.NewReader(part, boundary),
            )
            if nestedErr != nil {
                continue
            }

            if plain == "" && strings.TrimSpace(nestedPlain) != "" {
                plain = nestedPlain
            }
            if htmlText == "" && strings.TrimSpace(nestedHTML) != "" {
                htmlText = nestedHTML
            }
            continue
        }

        bodyBytes, readErr := decodePartBody(part)
        if readErr != nil {
            continue
        }

        bodyText := normalizeEmailText(string(bodyBytes))
        if bodyText == "" {
            continue
        }

        switch {
        case strings.HasPrefix(mediaType, "text/plain"):
            if plain == "" {
                plain = bodyText
            }
        case strings.HasPrefix(mediaType, "text/html"):
            if htmlText == "" {
                htmlText = stripHTMLToText(bodyText)
            }
        }
    }
}

func extractBodyFromRawEmail(raw string) string {
    raw = strings.TrimSpace(raw)
    if raw == "" {
        return ""
    }

    msg, err := mail.ReadMessage(bytes.NewReader([]byte(raw)))
    if err != nil {
        return normalizeEmailText(raw)
    }

    contentType := msg.Header.Get("Content-Type")
    mediaType, params, err := mime.ParseMediaType(contentType)
    if err != nil || mediaType == "" {
        bodyBytes, readErr := io.ReadAll(msg.Body)
        if readErr != nil {
            return normalizeEmailText(raw)
        }
        body := normalizeEmailText(string(bodyBytes))
        if body == "" {
            return normalizeEmailText(raw)
        }
        return body
    }

    mediaType = strings.ToLower(strings.TrimSpace(mediaType))

    if !strings.HasPrefix(mediaType, "multipart/") {
        bodyBytes, readErr := io.ReadAll(msg.Body)
        if readErr != nil {
            return normalizeEmailText(raw)
        }

        body := normalizeEmailText(string(bodyBytes))
        if strings.HasPrefix(mediaType, "text/html") {
            body = stripHTMLToText(body)
        }

        if body == "" {
            return normalizeEmailText(raw)
        }
        return body
    }

    boundary := strings.TrimSpace(params["boundary"])
    if boundary == "" {
        bodyBytes, readErr := io.ReadAll(msg.Body)
        if readErr != nil {
            return normalizeEmailText(raw)
        }
        body := normalizeEmailText(string(bodyBytes))
        if body == "" {
            return normalizeEmailText(raw)
        }
        return body
    }

    plain, htmlText, err := extractPreferredTextFromMultipartReader(
        multipart.NewReader(msg.Body, boundary),
    )
    if err == nil {
        if strings.TrimSpace(plain) != "" {
            return plain
        }
        if strings.TrimSpace(htmlText) != "" {
            return htmlText
        }
    }

    return normalizeEmailText(raw)
}

func quoteEmailBody(text string) string {
    normalized := normalizeEmailText(text)
    if normalized == "" {
        return ""
    }

    lines := strings.Split(normalized, "\n")
    for i, line := range lines {
        if strings.TrimSpace(line) == "" {
            lines[i] = ">"
        } else {
            lines[i] = "> " + line
        }
    }

    return strings.Join(lines, "\n")
}

func buildForwardBody(ctx *EmailReplyContext) string {
	var sb strings.Builder

	sb.WriteString("\n\n")
	sb.WriteString("---------- Пересылаемое сообщение ----------\n")

	if strings.TrimSpace(ctx.EmailFrom) != "" {
		sb.WriteString("От: ")
		sb.WriteString(strings.TrimSpace(ctx.EmailFrom))
		sb.WriteString("\n")
	}

	if !ctx.EmailDate.IsZero() {
		sb.WriteString("Дата: ")
		sb.WriteString(ctx.EmailDate.Format(time.RFC1123Z))
		sb.WriteString("\n")
	}

	if strings.TrimSpace(ctx.EmailSubject) != "" {
		sb.WriteString("Тема: ")
		sb.WriteString(strings.TrimSpace(ctx.EmailSubject))
		sb.WriteString("\n")
	}

	sb.WriteString("\n")

	rawBody := extractBodyFromRawEmail(ctx.RawEmail)
    if strings.TrimSpace(rawBody) != "" {
        sb.WriteString(rawBody)
    }

	return sb.String()
}

func buildReplyBody(ctx *EmailReplyContext) string {
    var sb strings.Builder

    originalBody := extractBodyFromRawEmail(ctx.RawEmail)

    sb.WriteString("\n\n")

    if !ctx.EmailDate.IsZero() || strings.TrimSpace(ctx.EmailFrom) != "" {
        if !ctx.EmailDate.IsZero() {
            sb.WriteString("Дата: ")
            sb.WriteString(ctx.EmailDate.Format(time.RFC1123Z))
        }

        if strings.TrimSpace(ctx.EmailFrom) != "" {
            if !ctx.EmailDate.IsZero() {
                sb.WriteString("\n")
            }
            sb.WriteString("От: ")
            sb.WriteString(strings.TrimSpace(ctx.EmailFrom))
        }

        sb.WriteString("\n")
    }

    sb.WriteString("---------- Ответ на письмо ----------\n")

    if quoted := quoteEmailBody(originalBody); strings.TrimSpace(quoted) != "" {
        sb.WriteString(quoted)
    }

    return strings.TrimRight(sb.String(), "\n")
}

// NewDBRepo — создаёт репозиторий с Postgres и MinIO.
func NewDBRepo(db *api.DB, incomingStore, outgoingStore *minio.CloudStorage) Repository {
    return &DBRepo{
        db:            db,
        incomingStore: incomingStore,
        outgoingStore: outgoingStore,
    }
}

// GetUserMailAuth достаёт из users email и почтовые OAuth‑токены.
func GetUserMailAuth(db *api.DB, userID int64) (*UserMailAuth, error) {
	row := db.Conn.QueryRow(`
        SELECT
            email,
            mail_access_token,
            mail_refresh_token,
            mail_access_expires_at
        FROM users
        WHERE id = $1
    `, userID)

	var email string
	var accessToken sql.NullString
	var refreshToken sql.NullString
	var accessExpiresAt sql.NullTime

	if err := row.Scan(&email, &accessToken, &refreshToken, &accessExpiresAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("user not found: id=%d", userID)
		}
		return nil, fmt.Errorf("query user mail auth: %w", err)
	}

	if !accessToken.Valid || accessToken.String == "" {
		return nil, fmt.Errorf("user id=%d has no mail_access_token", userID)
	}

	if !accessExpiresAt.Valid {
		return nil, fmt.Errorf("user id=%d has no mail_access_expires_at", userID)
	}

	auth := &UserMailAuth{
		Email:           email,
		AccessToken:     accessToken.String,
		AccessExpiresAt: accessExpiresAt.Time,
	}

	if refreshToken.Valid {
		auth.RefreshToken = refreshToken.String
	}

	return auth, nil
}

func GetUserMailAuthByEmail(db *api.DB, mailbox string) (*UserMailAuth, error) {
    row := db.Conn.QueryRow(`
        SELECT
            email,
            mail_access_token,
            mail_refresh_token,
            mail_access_expires_at
        FROM users
        WHERE lower(email) = lower($1)
        LIMIT 1
    `, mailbox)

    var email string
    var accessToken sql.NullString
    var refreshToken sql.NullString
    var accessExpiresAt sql.NullTime

    if err := row.Scan(&email, &accessToken, &refreshToken, &accessExpiresAt); err != nil {
        if err == sql.ErrNoRows {
            return nil, fmt.Errorf("user not found for mailbox=%s", mailbox)
        }
        return nil, fmt.Errorf("query user mail auth by email: %w", err)
    }

    if !accessToken.Valid || accessToken.String == "" {
        return nil, fmt.Errorf("mailbox=%s has no mail_access_token", mailbox)
    }

    if !accessExpiresAt.Valid {
        return nil, fmt.Errorf("mailbox=%s has no mail_access_expires_at", mailbox)
    }

    auth := &UserMailAuth{
        Email:           email,
        AccessToken:     accessToken.String,
        AccessExpiresAt: accessExpiresAt.Time,
    }

    if refreshToken.Valid {
        auth.RefreshToken = refreshToken.String
    }

    return auth, nil
}

func GetUserByEmail(db *api.DB, mailbox string) (int64, string, error) {
    row := db.Conn.QueryRow(`
        SELECT id, email
        FROM users
        WHERE lower(email) = lower($1)
        LIMIT 1
    `, mailbox)

    var userID int64
    var email string

    if err := row.Scan(&userID, &email); err != nil {
        if err == sql.ErrNoRows {
            return 0, "", fmt.Errorf("user not found for mailbox=%s", mailbox)
        }
        return 0, "", fmt.Errorf("query user by email: %w", err)
    }

    return userID, email, nil
}

// SaveOrder — сохраняет письмо и вложения в MinIO, а метаданные — в emails/documents/tasks.
func (r *DBRepo) SaveOrder(userID int64, order any) (err error) {
	email, ok := order.(parser.Email)
	if !ok {
		return fmt.Errorf("SaveOrder: expected parser.Email, got %T", order)
	}

	ctx := context.Background()
	emailUID := int64(email.UID)

	// Получаем email пользователя (для логики / MinIO-ключей)
	var userEmail string
	row := r.db.Conn.QueryRowContext(ctx, `
        SELECT email
        FROM users
        WHERE id = $1
    `, userID)
	if scanErr := row.Scan(&userEmail); scanErr != nil {
		if scanErr == sql.ErrNoRows {
			return fmt.Errorf("SaveOrder: user not found id=%d", userID)
		}
		return fmt.Errorf("SaveOrder: get user email: %w", scanErr)
	}

	// Поля письма (в виде обычных значений, не указателей)
	emailFromValue := ""
	if email.From != "" {
		emailFromValue = email.From
	}

	    replyToValue := ""
    if email.ReplyTo != "" {
        replyToValue = email.ReplyTo
    }

    messageIDValue := ""
    if email.MessageID != "" {
        messageIDValue = email.MessageID
    }

    inReplyToValue := ""
    if email.InReplyTo != "" {
        inReplyToValue = email.InReplyTo
    }

    referencesHeaderValue := ""
    if email.ReferencesHeader != "" {
        referencesHeaderValue = email.ReferencesHeader
    }

	emailSubjectValue := ""
	if email.Subject != "" {
		emailSubjectValue = email.Subject
	}

	rawEmailValue := ""
	if email.Body != "" {
		rawEmailValue = email.Body
	}

	var emailDateValue time.Time
    if strings.TrimSpace(email.Date) != "" {
        if parsed, parseErr := time.Parse(time.RFC3339, strings.TrimSpace(email.Date)); parseErr == nil {
            emailDateValue = parsed.UTC()
        }
    }
    if emailDateValue.IsZero() {
        emailDateValue = time.Now().UTC()
    }

    toHeaderValue := ""
	if email.To != "" {
		toHeaderValue = email.To
	}

	ccHeaderValue := ""
	if email.Cc != "" {
		ccHeaderValue = email.Cc
	}

	deliveredToValue := ""
	if email.DeliveredTo != "" {
		deliveredToValue = email.DeliveredTo
	}

	xOriginalToValue := ""
	if email.XOriginalTo != "" {
		xOriginalToValue = email.XOriginalTo
	}

	envelopeToValue := ""
	if email.EnvelopeTo != "" {
		envelopeToValue = email.EnvelopeTo
	}

	xEnvelopeToValue := ""
	if email.XEnvelopeTo != "" {
		xEnvelopeToValue = email.XEnvelopeTo
	}

	recipientEmailValue := ""
	if email.RecipientEmail != "" {
		recipientEmailValue = email.RecipientEmail
	}

	recipientSourceValue := ""
	if email.RecipientSource != "" {
		recipientSourceValue = email.RecipientSource
	}

	tx, err := r.db.Conn.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()

	// emails: upsert по (mailbox, email_uid)
	emailID, err := r.db.UpsertEmailTx(ctx, tx, api.EmailRecord{
		UserID:           userID,
        Mailbox:          userEmail,
        EmailUID:         emailUID,
        EmailFrom:        emailFromValue,
        ReplyTo:          replyToValue,
        MessageID:        messageIDValue,
        InReplyTo:        inReplyToValue,
        ReferencesHeader: referencesHeaderValue,
        EmailSubject:     emailSubjectValue,
        RawEmail:         rawEmailValue,
        EmailDate:        emailDateValue,
        ToHeader:           toHeaderValue,
		CcHeader:           ccHeaderValue,
		DeliveredTo:        deliveredToValue,
		XOriginalTo:        xOriginalToValue,
		EnvelopeTo:         envelopeToValue,
		XEnvelopeTo:        xEnvelopeToValue,
		RecipientEmail:     recipientEmailValue,
		RecipientSource:    recipientSourceValue,
		IsPrimaryRecipient: email.IsPrimaryRecipient,
    })
	if err != nil {
		return fmt.Errorf("upsert email (user_id=%d, uid=%d): %w", userID, emailUID, err)
	}

	// Сохраняем вложения в MinIO и documents
	var firstDocumentID *int64

	if len(email.Files) > 0 {
		for i, f := range email.Files {
			name := f.Name
			// Ключ в MinIO: userID/uid/index_name
			objectKey := fmt.Sprintf("%d/%d/%d_%s", userID, emailUID, i+1, name)

			if upErr := r.incomingStore.Upload(ctx, objectKey, f.Data); upErr != nil {
				err = fmt.Errorf("upload attachment %s (key=%s): %w", name, objectKey, upErr)
				return err
			}

			// В новой схеме documents
			docID, insErr := r.db.InsertDocumentTx(ctx, tx, api.DocumentRecord{
				EmailID:        emailID,
				Filename:       name,
				MinioObjectKey: objectKey,
				ContentType:    "", // при желании можно взять из f
				SizeBytes:      int64(len(f.Data)),
			})
			if insErr != nil {
				return fmt.Errorf("insert document (email_id=%d, key=%s): %w", emailID, objectKey, insErr)
			}

			if firstDocumentID == nil {
				firstDocumentID = &docID
			}
		}
	}

	// Создаём стартовую задачу классификации письма
	_, err = r.db.CreateTaskTx(ctx, tx, api.TaskRecord{
		EmailID:        emailID,
		DocumentID:     firstDocumentID,
		Status:         "new",
		OutputData:     json.RawMessage(`{}`),
		ManualDecision: nil,
		AssignedTo:     nil,
		ErrorMessage:   nil,
		RetryCount:     0,
		CompletedAt:    nil,
	})
	if err != nil {
		return fmt.Errorf("create classify_email task (email_id=%d): %w", emailID, err)
	}

	if err = tx.Commit(); err != nil {
		return fmt.Errorf("commit tx: %w", err)
	}

	return nil
}

// HasEmail — проверяет, есть ли уже письмо в emails по (mailbox, email_uid).
func (r DBRepo) HasEmail(mailbox string, emailUID int64) (bool, error) {
	ctx := context.Background()
	return r.db.HasEmail(ctx, mailbox, emailUID)
}

// UpdateUserMailTokens — обновляет почтовые токены пользователя в таблице users.
func UpdateUserMailTokens(db *api.DB, userID int64, auth *UserMailAuth) error {
	_, err := db.Conn.Exec(`
        UPDATE users
        SET
            mail_access_token = $1,
            mail_refresh_token = $2,
            mail_access_expires_at = $3
        WHERE id = $4
    `,
		auth.AccessToken,
		auth.RefreshToken,
		auth.AccessExpiresAt,
		userID,
	)
	if err != nil {
		return fmt.Errorf("update user mail tokens: %w", err)
	}
	return nil
}

// GetUsersWithMailAuth — возвращает всех пользователей, у которых есть почтовые токены.
func GetUsersWithMailAuth(db *api.DB) ([]MailUser, error) {
	rows, err := db.Conn.Query(`
        SELECT id, email
        FROM users
        WHERE mail_access_token IS NOT NULL
          AND mail_access_expires_at IS NOT NULL
        ORDER BY id
    `)
	if err != nil {
		return nil, fmt.Errorf("query users with mail auth: %w", err)
	}
	defer rows.Close()

	var users []MailUser
	for rows.Next() {
		var u MailUser
		if err := rows.Scan(&u.ID, &u.Email); err != nil {
			return nil, fmt.Errorf("scan user with mail auth: %w", err)
		}
		users = append(users, u)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows users with mail auth: %w", err)
	}

	return users, nil
}

func (r *DBRepo) SaveSentEmailWithAttachments(
    ctx context.Context,
    rec api.SentEmailRecord,
    attachments []SentAttachment,
) (int64, error) {
    if rec.UserID == nil {
        return 0, fmt.Errorf("sent email user_id is nil")
    }

    tx, err := r.db.Conn.Begin()
    if err != nil {
        return 0, err
    }
    defer func() {
        _ = tx.Rollback()
    }()

    sentEmailID, err := api.InsertSentEmailTx(tx, rec)
    if err != nil {
        return 0, err
    }

    for i, att := range attachments {
        objectKey := fmt.Sprintf("%d/%d/%d_%s", *rec.UserID, sentEmailID, i+1, att.Filename)

        if err := r.outgoingStore.Upload(ctx, objectKey, att.Data); err != nil {
            return 0, err
        }

        docRec := api.SentDocumentRecord{
            SentEmailID:   sentEmailID,
            Filename:      att.Filename,
            MinioObjectKey: objectKey,
            ContentType:   att.ContentType,
            SizeBytes:     int64(len(att.Data)),
            CreatedAt:     time.Now(),
        }

        if _, err := api.InsertSentDocumentTx(tx, docRec); err != nil {
            return 0, err
        }
    }

    if err := tx.Commit(); err != nil {
        return 0, err
    }

    return sentEmailID, nil
}

func GetForwardContext(db *api.DB, emailID int64, sourceType string) (*EmailReplyContext, error) {
    switch normalizeSourceType(sourceType) {
    case "sent":
        return GetSentEmailReplyContext(db, emailID)
    default:
        return GetEmailReplyContext(db, emailID)
    }
}

func GetSentEmailReplyContext(db *api.DB, emailID int64) (*EmailReplyContext, error) {
    row := db.Conn.QueryRow(`
        SELECT
            id,
            user_id,
            mailbox,
            email_from,
            reply_to,
            message_id,
            in_reply_to,
            references_header,
            email_subject,
            raw_email,
            email_date
        FROM sent_emails
        WHERE id = $1
    `, emailID)

    var (
        id               int64
        userID           sql.NullInt64
        mailbox          sql.NullString
        emailFrom        sql.NullString
        replyTo          sql.NullString
        messageID        sql.NullString
        inReplyTo        sql.NullString
        referencesHeader sql.NullString
        emailSubject     sql.NullString
        rawEmail         sql.NullString
        emailDate        sql.NullTime
    )

    if err := row.Scan(
        &id,
        &userID,
        &mailbox,
        &emailFrom,
        &replyTo,
        &messageID,
        &inReplyTo,
        &referencesHeader,
        &emailSubject,
        &rawEmail,
        &emailDate,
    ); err != nil {
        if err == sql.ErrNoRows {
            return nil, fmt.Errorf("sent email not found: id=%d", emailID)
        }
        return nil, fmt.Errorf("get sent email for reply: %w", err)
    }

    if !userID.Valid {
        return nil, fmt.Errorf("sent email id=%d has NULL user_id", emailID)
    }

    var dt time.Time
    if emailDate.Valid {
        dt = emailDate.Time
    }

    return &EmailReplyContext{
        EmailID:          id,
        UserID:           userID.Int64,
        Mailbox:          mailbox.String,
        EmailFrom:        emailFrom.String,
        ReplyTo:          replyTo.String,
        MessageID:        messageID.String,
        InReplyTo:        inReplyTo.String,
        ReferencesHeader: referencesHeader.String,
        EmailSubject:     emailSubject.String,
        RawEmail:         rawEmail.String,
        EmailDate:        dt,
    }, nil
}

func GetEmailReplyContext(db *api.DB, emailID int64) (*EmailReplyContext, error) {
    rec, err := db.GetEmailForReply(context.Background(), emailID)
    if err != nil {
        if err == sql.ErrNoRows {
            return nil, fmt.Errorf("email not found: id=%d", emailID)
        }
        return nil, fmt.Errorf("get email for reply: %w", err)
    }

    if !rec.UserID.Valid {
        return nil, fmt.Errorf("email id=%d has NULL user_id", emailID)
    }

    var emailDate time.Time
    if rec.EmailDate.Valid {
        emailDate = rec.EmailDate.Time
    }

    return &EmailReplyContext{
        EmailID:          rec.ID,
        UserID:           rec.UserID.Int64,
        Mailbox:          rec.Mailbox,
        EmailFrom:        rec.EmailFrom,
        ReplyTo:          rec.ReplyTo,
        MessageID:        rec.MessageID,
        InReplyTo:        rec.InReplyTo,
        ReferencesHeader: rec.ReferencesHeader,
        EmailSubject:     rec.EmailSubject,
        RawEmail:         rec.RawEmail,
        EmailDate:        emailDate,
    }, nil
}

func BuildForwardDraft(db *api.DB, emailID int64, sourceType string) (*ForwardDraft, error) {
    normalizedSource := normalizeSourceType(sourceType)

    ctx, err := GetForwardContext(db, emailID, normalizedSource)
    if err != nil {
        return nil, err
    }

    attachments := make([]ForwardAttachment, 0)

    if normalizedSource == "sent" {
        docs, err := ListSentDocumentsByEmailID(db, emailID)
        if err != nil {
            return nil, fmt.Errorf("list sent documents by email: %w", err)
        }

        attachments = make([]ForwardAttachment, 0, len(docs))
        for _, doc := range docs {
            attachments = append(attachments, ForwardAttachment{
                DocumentID:  doc.ID,
                Filename:    doc.Filename,
                ContentType: doc.ContentType,
                SizeBytes:   doc.SizeBytes,
                Selected:    true,
            })
        }
    } else {
        docs, err := db.ListDocumentsByEmailID(context.Background(), emailID)
        if err != nil {
            return nil, fmt.Errorf("list documents by email: %w", err)
        }

        attachments = make([]ForwardAttachment, 0, len(docs))
        for _, doc := range docs {
            attachments = append(attachments, ForwardAttachment{
                DocumentID:  doc.ID,
                Filename:    doc.Filename,
                ContentType: doc.ContentType,
                SizeBytes:   doc.SizeBytes,
                Selected:    true,
            })
        }
    }

    return &ForwardDraft{
        EmailID:     ctx.EmailID,
        Mailbox:     ctx.Mailbox,
        To:          "",
        Subject:     buildForwardSubject(ctx.EmailSubject),
        Body:        buildForwardBody(ctx),
        Attachments: attachments,
    }, nil
}

func BuildReplyDraft(db *api.DB, emailID int64, sourceType string) (*ReplyDraft, error) {
    normalizedSource := normalizeSourceType(sourceType)

    ctx, err := GetForwardContext(db, emailID, normalizedSource)
    if err != nil {
        return nil, err
    }

    to, err := extractReplyAddress(ctx.ReplyTo, ctx.EmailFrom)
    if err != nil {
        return nil, fmt.Errorf("build reply draft recipient: %w", err)
    }

    return &ReplyDraft{
        EmailID: ctx.EmailID,
        Mailbox: ctx.Mailbox,
        To:      to,
        Subject: buildReplySubject(ctx.EmailSubject),
        Body:    buildReplyBody(ctx),
    }, nil
}

func sumSMTPAttachmentsSize(items []mailsmtp.Attachment) int {
	total := 0
	for _, item := range items {
		total += len(item.Data)
	}
	return total
}

// ReplyToEmail — формирует и отправляет ответ на письмо через SMTP.
func ReplyToEmail(db *api.DB, repo *DBRepo, smtpClient *mailsmtp.Client, imapCfg *config.Config, req ReplyToEmailRequest) error {
    if repo == nil {
        return fmt.Errorf("repo is nil")
    }

    ctx, err := GetEmailReplyContext(db, req.EmailID)
    if err != nil {
        return err
    }

    authData, err := GetUserMailAuth(db, ctx.UserID)
    if err != nil {
        return fmt.Errorf("get user mail auth: %w", err)
    }

    to, err := extractReplyAddress(ctx.ReplyTo, ctx.EmailFrom)
    if err != nil {
        return fmt.Errorf("reply-to email: %w", err)
    }

    subject := ctx.EmailSubject
    if subject == "" {
        subject = "Re:"
    } else if !strings.HasPrefix(strings.ToLower(subject), "re:") {
        subject = "Re: " + subject
    }

    now := time.Now().UTC()
	messageID, err := generateMessageID(authData.Email, now)
	if err != nil {
		return fmt.Errorf("generate message id: %w", err)
	}

    headers := map[string]string{
        "From":         authData.Email,
        "To":           to,
        "Subject":      subject,
        "Date":         now.Format(time.RFC1123Z),
		"Message-ID":   messageID,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
    }

    parentMessageID := normalizeMessageID(ctx.MessageID)
    parentRefs := strings.TrimSpace(ctx.ReferencesHeader)

    if parentMessageID != "" {
        headers["In-Reply-To"] = parentMessageID
    }

    referencesValue := ""
    if parentRefs != "" && parentMessageID != "" {
        referencesValue = parentRefs + " " + parentMessageID
        headers["References"] = referencesValue
    } else if parentMessageID != "" {
        referencesValue = parentMessageID
        headers["References"] = referencesValue
    }

    auth := mailsmtp.AuthXOAuth2(authData.Email, authData.AccessToken)

    var raw []byte

    if len(req.Attachments) == 0 {
        raw, err = smtpClient.SendPlainText(
            authData.Email,
            []string{to},
            headers,
            req.Body,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send reply smtp: %w", err)
        }
    } else {
        smtpAttachments := make([]mailsmtp.Attachment, 0, len(req.Attachments))
        for _, att := range req.Attachments {
            smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
                Filename:    att.Filename,
                ContentType: att.ContentType,
                Data:        att.Data,
            })
        }

        raw, err = smtpClient.SendWithAttachments(
            authData.Email,
            []string{to},
            headers,
            req.Body,
            smtpAttachments,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send reply smtp with attachments: %w", err)
        }
    }

    sentRec := api.SentEmailRecord{
        UserID:           &ctx.UserID,
        Mailbox:          authData.Email,
        EmailUID:         nil,
        MessageID:        messageID,
        InReplyTo:        parentMessageID,
        ReferencesHeader: referencesValue,
        ParentEmailID:    &ctx.EmailID,
        EmailFrom:        authData.Email,
        ReplyTo:          "",
        ToHeader:         to,
        CcHeader:         "",
        BccHeader:        "",
        EmailSubject:     subject,
        RawEmail:         string(raw),
        EmailDate:        &now,
        SendStatus:       "sent",
        CreatedAt:        now,
        SentAt:           now,
    }

    sentAttachments := make([]SentAttachment, 0, len(req.Attachments))
    for _, att := range req.Attachments {
        sentAttachments = append(sentAttachments, SentAttachment{
            Filename:    att.Filename,
            ContentType: att.ContentType,
            Data:        att.Data,
        })
    }

    if _, err := repo.SaveSentEmailWithAttachments(context.Background(), sentRec, sentAttachments); err != nil {
        return fmt.Errorf("save sent reply: %w", err)
    }

    go func(rawMsg []byte, auth *UserMailAuth) {
        if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
            fmt.Printf("append to Sent failed: %v\n", err)
        }
    }(raw, authData)

    return nil
}

func SendEmail(db *api.DB, repo *DBRepo, smtpClient *mailsmtp.Client, imapCfg *config.Config, req SendEmailRequest) error {
    if repo == nil {
        return fmt.Errorf("repo is nil")
    }

    mailbox := strings.TrimSpace(req.Mailbox)
    if mailbox == "" {
        return fmt.Errorf("mailbox is empty")
    }

    userID, normalizedMailbox, err := GetUserByEmail(db, mailbox)
    if err != nil {
        return fmt.Errorf("get user by mailbox: %w", err)
    }

    authData, err := GetUserMailAuthByEmail(db, mailbox)
    if err != nil {
        return fmt.Errorf("get user mail auth by mailbox: %w", err)
    }

    recipients, err := parseRecipients(req.To)
    if err != nil {
        return fmt.Errorf("parse recipients: %w", err)
    }

    subject := strings.TrimSpace(req.Subject)
    now := time.Now().UTC()

	messageID, err := generateMessageID(authData.Email, now)
	if err != nil {
		return fmt.Errorf("generate message id: %w", err)
	}

    headers := map[string]string{
        "From":         authData.Email,
        "To":           strings.Join(recipients, ", "),
        "Subject":      subject,
        "Date":         now.Format(time.RFC1123Z),
		"Message-ID":   messageID,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
    }

    auth := mailsmtp.AuthXOAuth2(authData.Email, authData.AccessToken)

    var raw []byte

    if len(req.Attachments) == 0 {
        raw, err = smtpClient.SendPlainText(
            authData.Email,
            recipients,
            headers,
            req.Body,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send smtp: %w", err)
        }
    } else {
        smtpAttachments := make([]mailsmtp.Attachment, 0, len(req.Attachments))
        for _, att := range req.Attachments {
            smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
                Filename:    att.Filename,
                ContentType: att.ContentType,
                Data:        att.Data,
            })
        }

        raw, err = smtpClient.SendWithAttachments(
            authData.Email,
            recipients,
            headers,
            req.Body,
            smtpAttachments,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send smtp with attachments: %w", err)
        }
    }

    sentRec := api.SentEmailRecord{
        UserID:           &userID,
        Mailbox:          normalizedMailbox,
        EmailUID:         nil,
        MessageID:        messageID,
        InReplyTo:        "",
        ReferencesHeader: "",
        ParentEmailID:    nil,
        EmailFrom:        authData.Email,
        ReplyTo:          "",
        ToHeader:         strings.Join(recipients, ", "),
        CcHeader:         "",
        BccHeader:        "",
        EmailSubject:     subject,
        RawEmail:         string(raw),
        EmailDate:        &now,
        SendStatus:       "sent",
        CreatedAt:        now,
        SentAt:           now,
    }

    sentAttachments := make([]SentAttachment, 0, len(req.Attachments))
    for _, att := range req.Attachments {
        sentAttachments = append(sentAttachments, SentAttachment{
            Filename:    att.Filename,
            ContentType: att.ContentType,
            Data:        att.Data,
        })
    }

    if _, err := repo.SaveSentEmailWithAttachments(context.Background(), sentRec, sentAttachments); err != nil {
        return fmt.Errorf("save sent email: %w", err)
    }

    go func(rawMsg []byte, auth *UserMailAuth) {
        if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
            fmt.Printf("append to Sent failed: %v\n", err)
        }
    }(raw, authData)

    return nil
}

func ForwardEmail(db *api.DB, repo *DBRepo, smtpClient *mailsmtp.Client, imapCfg *config.Config, req ForwardEmailRequest) error {
    sourceType := normalizeSourceType(req.SourceType)

    ctxReply, err := GetForwardContext(db, req.EmailID, sourceType)
    if err != nil {
        return err
    }

    if repo == nil {
        return fmt.Errorf("repo is nil")
    }
    if req.EmailID <= 0 {
        return fmt.Errorf("email id is invalid")
    }

    toRaw := strings.TrimSpace(req.To)
    if toRaw == "" {
        return fmt.Errorf("to is empty")
    }

    body := strings.TrimSpace(req.Body)
    if body == "" {
        return fmt.Errorf("body is empty")
    }

    authData, err := GetUserMailAuth(db, ctxReply.UserID)
    if err != nil {
        return fmt.Errorf("get user mail auth: %w", err)
    }

    recipients, err := parseRecipients(toRaw)
    if err != nil {
        return fmt.Errorf("parse recipients: %w", err)
    }

    subject := buildForwardSubject(ctxReply.EmailSubject)

    smtpAttachments := make([]mailsmtp.Attachment, 0, len(req.IncludeDocumentIDs)+len(req.Attachments))

    if sourceType == "sent" {
        selectedDocs, err := ListSentDocumentsByIDsForEmail(db, req.EmailID, req.IncludeDocumentIDs)
        if err != nil {
            return fmt.Errorf("list selected sent documents: %w", err)
        }

        for _, doc := range selectedDocs {
            data, err := repo.outgoingStore.Download(context.Background(), doc.MinioObjectKey)
            if err != nil {
                return fmt.Errorf("download sent attachment document_id=%d: %w", doc.ID, err)
            }

            smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
                Filename:    doc.Filename,
                ContentType: doc.ContentType,
                Data:        data,
            })
        }
    } else {
        selectedDocs, err := db.ListDocumentsByIDsForEmail(context.Background(), req.EmailID, req.IncludeDocumentIDs)
        if err != nil {
            return fmt.Errorf("list selected documents: %w", err)
        }

        for _, doc := range selectedDocs {
            data, err := repo.incomingStore.Download(context.Background(), doc.MinioObjectKey)
            if err != nil {
                return fmt.Errorf("download attachment document_id=%d: %w", doc.ID, err)
            }

            smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
                Filename:    doc.Filename,
                ContentType: doc.ContentType,
                Data:        data,
            })
        }
    }

    // Новые вложения, добавленные при пересылке
    for _, att := range req.Attachments {
        smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
            Filename:    att.Filename,
            ContentType: att.ContentType,
            Data:        att.Data,
        })
    }

    const maxTotalAttachmentsSize = 25 << 20 // 25 MB
    if sumSMTPAttachmentsSize(smtpAttachments) > maxTotalAttachmentsSize {
        return fmt.Errorf("вес превышен: общий вес письма выше 25МБ")
    }

    now := time.Now().UTC()

	messageID, err := generateMessageID(authData.Email, now)
	if err != nil {
		return fmt.Errorf("generate message id: %w", err)
	}

    headers := map[string]string{
        "From":         authData.Email,
        "To":           strings.Join(recipients, ", "),
        "Subject":      subject,
        "Date":         now.Format(time.RFC1123Z),
		"Message-ID":   messageID,
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
    }

    auth := mailsmtp.AuthXOAuth2(authData.Email, authData.AccessToken)

    var raw []byte

    if len(smtpAttachments) == 0 {
        raw, err = smtpClient.SendPlainText(
            authData.Email,
            recipients,
            headers,
            body,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send forward smtp: %w", err)
        }
    } else {
        raw, err = smtpClient.SendWithAttachments(
            authData.Email,
            recipients,
            headers,
            body,
            smtpAttachments,
            auth,
        )
        if err != nil {
            return fmt.Errorf("send forward smtp with attachments: %w", err)
        }
    }

    // Сохранение пересылки
    sentRec := api.SentEmailRecord{
        UserID:           &ctxReply.UserID,
        Mailbox:          authData.Email,
        EmailUID:         nil,
        MessageID:        messageID,
        InReplyTo:        "",
        ReferencesHeader: "",
        ParentEmailID:    &ctxReply.EmailID,
        EmailFrom:        authData.Email,
        ReplyTo:          "",
        ToHeader:         strings.Join(recipients, ", "),
        CcHeader:         "",
        BccHeader:        "",
        EmailSubject:     subject,
        RawEmail:         string(raw),
        EmailDate:        &now,
        SendStatus:       "sent",
        CreatedAt:        now,
        SentAt:           now,
    }

    sentAttachments := make([]SentAttachment, 0, len(smtpAttachments))
    for _, att := range smtpAttachments {
        sentAttachments = append(sentAttachments, SentAttachment{
            Filename:    att.Filename,
            ContentType: att.ContentType,
            Data:        att.Data,
        })
    }

    if _, err := repo.SaveSentEmailWithAttachments(context.Background(), sentRec, sentAttachments); err != nil {
        return fmt.Errorf("save forwarded email: %w", err)
    }

    go func(rawMsg []byte, auth *UserMailAuth) {
        if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
            fmt.Printf("append to Sent failed: %v\n", err)
        }
    }(raw, authData)

    return nil
}