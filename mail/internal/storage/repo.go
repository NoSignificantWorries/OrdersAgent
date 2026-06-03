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

// ReplyToEmailRequest — данные для ответа на письмо.
type ReplyToEmailRequest struct {
    EmailID int64  // ID письма в таблице emails
    Body    string // Текст ответа (plain text)
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

// SaveOrder — сохраняет письмо и вложения в MinIO, а метаданные — в emails/documents/tasks.
func (r *DBRepo) SaveOrder(userID int64, order any) (err error) {
	// ВАЖНО: теперь ждём значение parser.Email, а не *parser.Email
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


// ReplyToEmail — формирует и отправляет ответ на письмо через SMTP.
func ReplyToEmail(db *api.DB, smtpClient *mailsmtp.Client, req ReplyToEmailRequest) error {
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

    if ctx.MessageID != "" {
        headers["In-Reply-To"] = ctx.MessageID
    }

    if ctx.ReferencesHeader != "" && ctx.MessageID != "" {
        headers["References"] = ctx.ReferencesHeader + " " + ctx.MessageID
    } else if ctx.MessageID != "" {
        headers["References"] = ctx.MessageID
    }

    // 6. SMTP auth — пока логика под пароль приложения.
    // Для Яндекс-почты: host smtp.yandex.ru, port 465/587. [web:26][web:20]
    //host := "smtp.yandex.ru"
    auth := mailsmtp.AuthXOAuth2(authData.Email, authData.AccessToken)

    // 7. Отправляем письмо.
    if err := smtpClient.SendPlainText(
        authData.Email,
        []string{to},
        headers,
        req.Body,
        auth,
    ); err != nil {
        return fmt.Errorf("send reply smtp: %w", err)
    }

    return nil
}