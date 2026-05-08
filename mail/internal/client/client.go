package client

import (
	"fmt"

	"OrdersAgent/mail/internal/config"
	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
)

type Client struct {
	conn *imapclient.Client
	cfg  *config.Config
}

// Новый конструктор по OAuth2 (XOAUTH2).
func NewOAuth(cfg *config.Config, email, accessToken string) (*Client, error) {
	c, err := imapclient.DialTLS(
		fmt.Sprintf("%s:%d", cfg.Host, cfg.Port),
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("dial: %w", err)
	}

	saslClient := &xoauth2Client{
		email:       email,
		accessToken: accessToken,
	}

	if err := c.Authenticate(saslClient); err != nil {
		c.Close()
		return nil, fmt.Errorf("authenticate XOAUTH2: %w", err)
	}

	if _, err := c.Select("INBOX", nil).Wait(); err != nil {
		c.Close()
		return nil, fmt.Errorf("select INBOX: %w", err)
	}

	return &Client{conn: c, cfg: cfg}, nil
}

func (c *Client) FetchUnread() ([]imap.UID, error) {
	criteria := &imap.SearchCriteria{}
	searchData, err := c.conn.UIDSearch(criteria, nil).Wait()
	if err != nil {
		return nil, fmt.Errorf("search: %w", err)
	}

	allUIDs := searchData.AllUIDs()
	if len(allUIDs) == 0 {
		return nil, nil
	}

	fetchOptions := &imap.FetchOptions{
		Flags: true,
		UID:   true,
	}

	fetchCmd := c.conn.Fetch(imap.UIDSetNum(allUIDs...), fetchOptions)
	defer fetchCmd.Close()

	messages, err := fetchCmd.Collect()
	if err != nil {
		return nil, fmt.Errorf("fetch flags: %w", err)
	}

	var unreadUIDs []imap.UID
	for _, msg := range messages {
		hasSeen := false
		for _, flag := range msg.Flags {
			if flag == "\\Seen" {
				hasSeen = true
				break
			}
		}
		if !hasSeen {
			unreadUIDs = append(unreadUIDs, msg.UID)
		}
	}

	return unreadUIDs, nil
}

func (c *Client) FetchMessage(uid imap.UID) (*imapclient.FetchCommand, error) {
	fetchOptions := &imap.FetchOptions{
		UID:      true,
		Envelope: true,
		BodySection: []*imap.FetchItemBodySection{{
			Peek: true,
		}},
	}

	return c.conn.Fetch(imap.UIDSetNum(uid), fetchOptions), nil
}

func (c *Client) MarkRead(uid imap.UID) error {
	storeFlags := imap.StoreFlags{
		Op:    imap.StoreFlagsAdd,
		Flags: []imap.Flag{"\\Seen"},
	}
	storeCmd := c.conn.Store(imap.UIDSetNum(uid), &storeFlags, nil)
	return storeCmd.Close()
}

func (c *Client) Close() error {
	return c.conn.Close()
}

// ---- минимальная реализация SASL XOAUTH2 ----

type xoauth2Client struct {
	email       string
	accessToken string
	done        bool
}

// Start начинает SASL-аутентификацию и возвращает:
// - механизм: XOAUTH2
// - initial response: user=<email>\x01auth=Bearer <token>\x01\x01
func (c *xoauth2Client) Start() (mech string, ir []byte, err error) {
	resp := fmt.Sprintf("user=%s\x01auth=Bearer %s\x01\x01", c.email, c.accessToken)
	c.done = true
	return "XOAUTH2", []byte(resp), nil
}

// Next вызывается, если сервер прислал challenge.
// Для XOAUTH2 обычно это не нужно; если пришёл challenge, отвечаем пустым ответом.
func (c *xoauth2Client) Next(challenge []byte) (response []byte, err error) {
	if c.done {
		return []byte{}, nil
	}
	c.done = true
	return []byte{}, nil
}