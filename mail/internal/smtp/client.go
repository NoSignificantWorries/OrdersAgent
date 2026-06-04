package smtp

import (
    "crypto/tls"
    "fmt"
	"mime"
    "net"
    "net/smtp"
    "strings"
    "time"
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

    addr := fmt.Sprintf("%s:%d", c.cfg.Host, c.cfg.Port)

    // Яндекс рекомендует TLS (465) или STARTTLS (587). [web:26][web:20]
    // Для простоты используем TLS-подключение (465).
    tlsConfig := &tls.Config{
        ServerName: c.cfg.Host,
    }

    conn, err := tls.DialWithDialer(&net.Dialer{Timeout: 10 * time.Second}, "tcp", addr, tlsConfig)
    if err != nil {
        return nil, fmt.Errorf("smtp: dial tls: %w", err)
    }
    defer conn.Close()

    client, err := smtp.NewClient(conn, c.cfg.Host)
    if err != nil {
        return nil, fmt.Errorf("smtp: new client: %w", err)
    }
    defer client.Quit()

    if auth != nil {
        if err := client.Auth(auth); err != nil {
            return nil, fmt.Errorf("smtp: auth: %w", err)
        }
    }

    if err := client.Mail(from); err != nil {
        return nil, fmt.Errorf("smtp: MAIL FROM: %w", err)
    }

    for _, rcpt := range to {
        if err := client.Rcpt(rcpt); err != nil {
            return nil, fmt.Errorf("smtp: RCPT TO %s: %w", rcpt, err)
        }
    }

    wc, err := client.Data()
    if err != nil {
        return nil, fmt.Errorf("smtp: DATA: %w", err)
    }

    if _, err := wc.Write(msg); err != nil {
        _ = wc.Close()
        return nil, fmt.Errorf("smtp: write message: %w", err)
    }

    if err := wc.Close(); err != nil {
        return nil, fmt.Errorf("smtp: close data: %w", err)
    }

    return msg, nil
}