package storage

import (
	"crypto/tls"
	"fmt"
	"log"
	"time"

	"mail/internal/config"

	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
)

type xoauth2IMAPClient struct {
	email       string
	accessToken string
	done        bool
}

func (c *xoauth2IMAPClient) Start() (mech string, ir []byte, err error) {
	resp := fmt.Sprintf("user=%s\x01auth=Bearer %s\x01\x01", c.email, c.accessToken)
	c.done = true
	return "XOAUTH2", []byte(resp), nil
}

func (c *xoauth2IMAPClient) Next(challenge []byte) (response []byte, err error) {
	if c.done {
		return []byte{}, nil
	}
	c.done = true
	return []byte{}, nil
}

func appendToSent(raw []byte, authData *UserMailAuth, imapCfg *config.Config) error {
	c, err := imapclient.DialTLS(
		fmt.Sprintf("%s:%d", imapCfg.Host, imapCfg.Port),
		&imapclient.Options{
			TLSConfig: &tls.Config{
				ServerName: imapCfg.Host,
			},
		},
	)
	if err != nil {
		return fmt.Errorf("imap dial: %w", err)
	}
	defer c.Close()

	saslClient := &xoauth2IMAPClient{
		email:       authData.Email,
		accessToken: authData.AccessToken,
	}

	if err := c.Authenticate(saslClient); err != nil {
		return fmt.Errorf("authenticate XOAUTH2: %w", err)
	}

	sentMailbox, err := detectSentMailbox(c)
	if err != nil {
		return fmt.Errorf("detect sent mailbox: %w", err)
	}

	appendCmd := c.Append(sentMailbox, int64(len(raw)), &imap.AppendOptions{
		Flags: []imap.Flag{imap.FlagSeen},
		Time:  time.Now(),
	})

	if _, err := appendCmd.Write(raw); err != nil {
		return fmt.Errorf("imap append write: %w", err)
	}

	if err := appendCmd.Close(); err != nil {
		return fmt.Errorf("imap append close: %w", err)
	}

	if _, err := appendCmd.Wait(); err != nil {
		return fmt.Errorf("imap append wait: %w", err)
	}

	log.Printf("append to Sent completed | email=%s mailbox=%q bytes=%d", authData.Email, sentMailbox, len(raw))
	return nil
}

func detectSentMailbox(c *imapclient.Client) (string, error) {
	candidates := []string{
		"Sent",
		"Sent Items",
		"INBOX.Sent",
		"Отправленные",
		"Отправленные письма",
		"[Gmail]/Sent Mail",
	}

	for _, name := range candidates {
		cmd := c.Select(name, nil)
		_, err := cmd.Wait()
		if err == nil {
			_ = c.Unselect().Wait()
			return name, nil
		}
	}

	return "", fmt.Errorf("sent mailbox not found")
}