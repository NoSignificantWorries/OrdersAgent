package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"time"
	"strings"
	"net/mail"

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
}

// DBRepo — пишет метаданные в Postgres и файлы в MinIO.
type DBRepo struct {
	db    *api.DB
	store *minio.CloudStorage
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

	rawBody := strings.ReplaceAll(ctx.RawEmail, "\r\n", "\n")
	rawBody = strings.ReplaceAll(rawBody, "\r", "\n")
	sb.WriteString(rawBody)

	return sb.String()
}

// NewDBRepo — создаёт репозиторий с Postgres и MinIO.
func NewDBRepo(db *api.DB, store *minio.CloudStorage) Repository {
	return &DBRepo{
		db:    db,
		store: store,
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
	if email.Date != "" {
		if parsed, parseErr := time.Parse("2006-01-02 15:04", email.Date); parseErr == nil {
			emailDateValue = parsed
		}
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

			if upErr := r.store.Upload(ctx, objectKey, f.Data); upErr != nil {
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

func BuildForwardDraft(db *api.DB, emailID int64) (*ForwardDraft, error) {
	ctx, err := GetEmailReplyContext(db, emailID)
	if err != nil {
		return nil, err
	}

	docs, err := db.ListDocumentsByEmailID(context.Background(), emailID)
	if err != nil {
		return nil, fmt.Errorf("list documents by email: %w", err)
	}

	attachments := make([]ForwardAttachment, 0, len(docs))
	for _, doc := range docs {
		attachments = append(attachments, ForwardAttachment{
			DocumentID:  doc.ID,
			Filename:    doc.Filename,
			ContentType: doc.ContentType,
			SizeBytes:   doc.SizeBytes,
			Selected:    true,
		})
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

func sumSMTPAttachmentsSize(items []mailsmtp.Attachment) int {
	total := 0
	for _, item := range items {
		total += len(item.Data)
	}
	return total
}

// ReplyToEmail — формирует и отправляет ответ на письмо через SMTP.
func ReplyToEmail(db *api.DB, smtpClient *mailsmtp.Client, imapCfg *config.Config, req ReplyToEmailRequest) error {
    // 1. Получаем контекст письма (email + user_id).
    ctx, err := GetEmailReplyContext(db, req.EmailID)
    if err != nil {
        return err
    }

    // 2. Получаем почтовые токены пользователя.
    authData, err := GetUserMailAuth(db, ctx.UserID)
    if err != nil {
        return fmt.Errorf("get user mail auth: %w", err)
    }

    // 3. Определяем адрес, куда отвечать.
    to, err := extractReplyAddress(ctx.ReplyTo, ctx.EmailFrom)
	if err != nil {
		return fmt.Errorf("reply-to email: %w", err)
	}

    // 4. Формируем тему.
    subject := ctx.EmailSubject
    if subject == "" {
        subject = "Re:"
    } else if !strings.HasPrefix(strings.ToLower(subject), "re:") {
        subject = "Re: " + subject
    }

    // 5. Формируем заголовки для threading.
    headers := map[string]string{
        "From":         authData.Email,
        "To":           to,
        "Subject":      subject,
        "Date":         time.Now().UTC().Format(time.RFC1123Z),
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
    }

    parentMessageID := normalizeMessageID(ctx.MessageID)
	parentRefs := strings.TrimSpace(ctx.ReferencesHeader)

	if parentMessageID != "" {
		headers["In-Reply-To"] = parentMessageID
	}

	if parentRefs != "" && parentMessageID != "" {
		headers["References"] = parentRefs + " " + parentMessageID
	} else if parentMessageID != "" {
		headers["References"] = parentMessageID
	}

    // 6. SMTP auth — пока логика под пароль приложения.
    // Для Яндекс-почты: host smtp.yandex.ru, port 465/587. [web:26][web:20]
    //host := "smtp.yandex.ru"
    auth := mailsmtp.AuthXOAuth2(authData.Email, authData.AccessToken)

    // 7. Отправляем письмо.
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

	go func(rawMsg []byte, auth *UserMailAuth) {
    if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
			fmt.Printf("append to Sent failed: %v\n", err)
		}
	}(raw, authData)

	return nil
}

func SendEmail(db *api.DB, smtpClient *mailsmtp.Client, imapCfg *config.Config, req SendEmailRequest) error {
    mailbox := strings.TrimSpace(req.Mailbox)
    if mailbox == "" {
        return fmt.Errorf("mailbox is empty")
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
    headers := map[string]string{
        "From":         authData.Email,
        "To":           strings.Join(recipients, ", "),
        "Subject":      subject,
        "Date":         time.Now().UTC().Format(time.RFC1123Z),
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

    go func(rawMsg []byte, auth *UserMailAuth) {
        if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
            fmt.Printf("append to Sent failed: %v\n", err)
        }
    }(raw, authData)

    return nil
}

func ForwardEmail(db *api.DB, repo *DBRepo, smtpClient *mailsmtp.Client, imapCfg *config.Config, req ForwardEmailRequest) error {
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

	ctx, err := GetEmailReplyContext(db, req.EmailID)
	if err != nil {
		return err
	}

	authData, err := GetUserMailAuth(db, ctx.UserID)
	if err != nil {
		return fmt.Errorf("get user mail auth: %w", err)
	}

	recipients, err := parseRecipients(toRaw)
	if err != nil {
		return fmt.Errorf("parse recipients: %w", err)
	}

	subject := buildForwardSubject(ctx.EmailSubject)

	selectedDocs, err := db.ListDocumentsByIDsForEmail(context.Background(), req.EmailID, req.IncludeDocumentIDs)
	if err != nil {
		return fmt.Errorf("list selected documents: %w", err)
	}

	smtpAttachments := make([]mailsmtp.Attachment, 0, len(selectedDocs)+len(req.Attachments))

	for _, doc := range selectedDocs {
		data, err := repo.store.Download(context.Background(), doc.MinioObjectKey)
		if err != nil {
			return fmt.Errorf("download attachment document_id=%d: %w", doc.ID, err)
		}

		smtpAttachments = append(smtpAttachments, mailsmtp.Attachment{
			Filename:    doc.Filename,
			ContentType: doc.ContentType,
			Data:        data,
		})
	}

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

	headers := map[string]string{
		"From":         authData.Email,
		"To":           strings.Join(recipients, ", "),
		"Subject":      subject,
		"Date":         time.Now().UTC().Format(time.RFC1123Z),
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

	go func(rawMsg []byte, auth *UserMailAuth) {
		if err := appendToSent(rawMsg, auth, imapCfg); err != nil {
			fmt.Printf("append to Sent failed: %v\n", err)
		}
	}(raw, authData)

	return nil
}