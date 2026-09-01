package smtp

import (
    "crypto/tls"
    "fmt"
	"mime"
    "net"
    "net/smtp"
    "strings"
    "time"
    "encoding/base64"
    "math/rand"
    "net/http"
    "path/filepath"
)

// Config — настройки SMTP-сервера.
type Config struct {
    Host string
    Port int
}

// Client — SMTP-клиент.
type Client struct {
    cfg Config
}

type Attachment struct {
    Filename    string
    ContentType string
    Data        []byte
}

// NewClient — создаёт SMTP-клиент.
func NewClient(cfg Config) *Client {
    return &Client{cfg: cfg}
}

func firstNonEmpty(values ...string) string {
    for _, v := range values {
        if strings.TrimSpace(v) != "" {
            return v
        }
    }
    return ""
}

func encodeHeaderIfNeeded(v string) string {
    v = strings.TrimSpace(v)
    if v == "" {
        return ""
    }
    if isASCII(v) {
        return v
    }
    return mime.QEncoding.Encode("utf-8", v)
}

func isASCII(s string) bool {
    for i := 0; i < len(s); i++ {
        if s[i] > 127 {
            return false
        }
    }
    return true
}

func (c *Client) sendRawMessage(from string, to []string, msg []byte, auth smtp.Auth) error {
    if len(to) == 0 {
        return fmt.Errorf("smtp: no recipients")
    }

    addr := fmt.Sprintf("%s:%d", c.cfg.Host, c.cfg.Port)

    tlsConfig := &tls.Config{
        ServerName: c.cfg.Host,
    }

    conn, err := tls.DialWithDialer(&net.Dialer{Timeout: 10 * time.Second}, "tcp", addr, tlsConfig)
    if err != nil {
        return fmt.Errorf("smtp: dial tls: %w", err)
    }
    defer conn.Close()

    client, err := smtp.NewClient(conn, c.cfg.Host)
    if err != nil {
        return fmt.Errorf("smtp: new client: %w", err)
    }
    defer client.Quit()

    if auth != nil {
        if err := client.Auth(auth); err != nil {
            return fmt.Errorf("smtp: auth: %w", err)
        }
    }

    if err := client.Mail(from); err != nil {
        return fmt.Errorf("smtp: MAIL FROM: %w", err)
    }

    for _, rcpt := range to {
        if err := client.Rcpt(rcpt); err != nil {
            return fmt.Errorf("smtp: RCPT TO %s: %w", rcpt, err)
        }
    }

    wc, err := client.Data()
    if err != nil {
        return fmt.Errorf("smtp: DATA: %w", err)
    }

    if _, err := wc.Write(msg); err != nil {
        _ = wc.Close()
        return fmt.Errorf("smtp: write message: %w", err)
    }

    if err := wc.Close(); err != nil {
        return fmt.Errorf("smtp: close data: %w", err)
    }

    return nil
}

// SendPlainText — отправка простого text/plain письма с готовыми заголовками.
func (c *Client) SendPlainText(from string, to []string, headers map[string]string, body string, auth smtp.Auth) ([]byte, error) {
    if len(to) == 0 {
        return nil, fmt.Errorf("smtp: no recipients")
    }

    // Собираем заголовки в фиксированном порядке.
	var sb strings.Builder

	// Базовые заголовки
	fromHeader := firstNonEmpty(headers["From"], from)
	if strings.TrimSpace(fromHeader) != "" {
		sb.WriteString("From: ")
		sb.WriteString(fromHeader)
		sb.WriteString("\r\n")
	}

	toHeader := firstNonEmpty(headers["To"], strings.Join(to, ", "))
	if strings.TrimSpace(toHeader) != "" {
		sb.WriteString("To: ")
		sb.WriteString(toHeader)
		sb.WriteString("\r\n")
	}

	subjectHeader := encodeHeaderIfNeeded(headers["Subject"])
	if subjectHeader != "" {
		sb.WriteString("Subject: ")
		sb.WriteString(subjectHeader)
		sb.WriteString("\r\n")
	}

	dateHeader := firstNonEmpty(headers["Date"], time.Now().UTC().Format(time.RFC1123Z))
	sb.WriteString("Date: ")
	sb.WriteString(dateHeader)
	sb.WriteString("\r\n")

	mimeVer := firstNonEmpty(headers["MIME-Version"], "1.0")
	sb.WriteString("MIME-Version: ")
	sb.WriteString(mimeVer)
	sb.WriteString("\r\n")

	contentType := firstNonEmpty(headers["Content-Type"], "text/plain; charset=UTF-8")
	sb.WriteString("Content-Type: ")
	sb.WriteString(contentType)
	sb.WriteString("\r\n")

	// Остальные заголовки (включая In-Reply-To и References), кроме уже записанных базовых
	for k, v := range headers {
		v = strings.TrimSpace(v)
		if v == "" {
			continue
		}
		lower := strings.ToLower(k)
		if lower == "from" ||
			lower == "to" ||
			lower == "subject" ||
			lower == "date" ||
			lower == "mime-version" ||
			lower == "content-type" {
			continue
		}

		sb.WriteString(k)
		sb.WriteString(": ")
		sb.WriteString(v)
		sb.WriteString("\r\n")
	}

	normalizedBody := strings.ReplaceAll(body, "\r\n", "\n")
	normalizedBody = strings.ReplaceAll(normalizedBody, "\r", "\n")
	normalizedBody = strings.ReplaceAll(normalizedBody, "\n", "\r\n")

	// Пустая строка между заголовками и телом
	sb.WriteString("\r\n")
	sb.WriteString(normalizedBody)

	msg := []byte(sb.String())

    if err := c.sendRawMessage(from, to, msg, auth); err != nil {
        return nil, err
    }

    return msg, nil
}

func (c *Client) SendWithAttachments(
    from string,
    to []string,
    headers map[string]string,
    body string,
    attachments []Attachment,
    auth smtp.Auth,
) ([]byte, error) {
    if len(to) == 0 {
        return nil, fmt.Errorf("smtp: no recipients")
    }

    boundary := fmt.Sprintf("mixed-%d-%d", time.Now().UnixNano(), rand.Int())

    var sb strings.Builder

    fromHeader := firstNonEmpty(headers["From"], from)
    if strings.TrimSpace(fromHeader) != "" {
        sb.WriteString("From: ")
        sb.WriteString(fromHeader)
        sb.WriteString("\r\n")
    }

    toHeader := firstNonEmpty(headers["To"], strings.Join(to, ", "))
    if strings.TrimSpace(toHeader) != "" {
        sb.WriteString("To: ")
        sb.WriteString(toHeader)
        sb.WriteString("\r\n")
    }

    subjectHeader := encodeHeaderIfNeeded(headers["Subject"])
    if subjectHeader != "" {
        sb.WriteString("Subject: ")
        sb.WriteString(subjectHeader)
        sb.WriteString("\r\n")
    }

    dateHeader := firstNonEmpty(headers["Date"], time.Now().UTC().Format(time.RFC1123Z))
    sb.WriteString("Date: ")
    sb.WriteString(dateHeader)
    sb.WriteString("\r\n")

    sb.WriteString("MIME-Version: 1.0\r\n")
    sb.WriteString(fmt.Sprintf("Content-Type: multipart/mixed; boundary=%q\r\n", boundary))

    for k, v := range headers {
        v = strings.TrimSpace(v)
        if v == "" {
            continue
        }

        lower := strings.ToLower(k)
        if lower == "from" ||
            lower == "to" ||
            lower == "subject" ||
            lower == "date" ||
            lower == "mime-version" ||
            lower == "content-type" {
            continue
        }

        sb.WriteString(k)
        sb.WriteString(": ")
        sb.WriteString(v)
        sb.WriteString("\r\n")
    }

    normalizedBody := strings.ReplaceAll(body, "\r\n", "\n")
    normalizedBody = strings.ReplaceAll(normalizedBody, "\r", "\n")
    normalizedBody = strings.ReplaceAll(normalizedBody, "\n", "\r\n")

    sb.WriteString("\r\n")

    sb.WriteString("--" + boundary + "\r\n")
    sb.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
    sb.WriteString("Content-Transfer-Encoding: 8bit\r\n")
    sb.WriteString("\r\n")
    sb.WriteString(normalizedBody)
    sb.WriteString("\r\n")

    for _, att := range attachments {
        filename := strings.TrimSpace(att.Filename)
        if filename == "" {
            filename = "attachment"
        }

        contentType := strings.TrimSpace(att.ContentType)
        if contentType == "" {
            contentType = mime.TypeByExtension(filepath.Ext(filename))
        }
        if contentType == "" && len(att.Data) > 0 {
            contentType = http.DetectContentType(att.Data)
        }
        if contentType == "" {
            contentType = "application/octet-stream"
        }

        encodedFilename := encodeHeaderIfNeeded(filename)

        encoded := make([]byte, base64.StdEncoding.EncodedLen(len(att.Data)))
        base64.StdEncoding.Encode(encoded, att.Data)

        sb.WriteString("--" + boundary + "\r\n")
        sb.WriteString(fmt.Sprintf("Content-Type: %s; name=%s\r\n", contentType, encodedFilename))
        sb.WriteString("Content-Transfer-Encoding: base64\r\n")
        sb.WriteString(fmt.Sprintf("Content-Disposition: attachment; filename=%s\r\n", encodedFilename))
        sb.WriteString("\r\n")

        for i := 0; i < len(encoded); i += 76 {
            end := i + 76
            if end > len(encoded) {
                end = len(encoded)
            }
            sb.Write(encoded[i:end])
            sb.WriteString("\r\n")
        }
    }

    sb.WriteString("--" + boundary + "--\r\n")

    msg := []byte(sb.String())

    if err := c.sendRawMessage(from, to, msg, auth); err != nil {
        return nil, err
    }

    return msg, nil
}