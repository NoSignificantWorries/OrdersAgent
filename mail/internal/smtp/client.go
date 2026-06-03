package smtp

import (
    "crypto/tls"
    "fmt"
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

// SendPlainText — отправка простого text/plain письма с готовыми заголовками.
func (c *Client) SendPlainText(from string, to []string, headers map[string]string, body string, auth smtp.Auth) error {
    if len(to) == 0 {
        return fmt.Errorf("smtp: no recipients")
    }

    // Собираем заголовки.
    var sb strings.Builder
    for k, v := range headers {
        if v == "" {
            continue
        }
        sb.WriteString(k)
        sb.WriteString(": ")
        sb.WriteString(v)
        sb.WriteString("\r\n")
    }
    sb.WriteString("\r\n")
    sb.WriteString(body)

    msg := []byte(sb.String())

    addr := fmt.Sprintf("%s:%d", c.cfg.Host, c.cfg.Port)

    // Яндекс рекомендует TLS (465) или STARTTLS (587). [web:26][web:20]
    // Для простоты используем TLS-подключение (465).
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