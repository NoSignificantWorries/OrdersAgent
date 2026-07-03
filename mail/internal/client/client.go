package client

import (
	"fmt"
	"log"
	"time"
	"sort"

	"mail/internal/config"

	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
)

type Client struct {
	conn        *imapclient.Client
	cfg         *config.Config
	email       string
	sessionID   string
	connectedAt time.Time
	lastOKAt    time.Time
}

func (c *Client) SessionID() string {
    if c == nil {
        return ""
    }
    return c.sessionID
}

func (c *Client) Email() string {
    if c == nil {
        return ""
    }
    return c.email
}

func (c *Client) ConnectedAt() time.Time {
    if c == nil {
        return time.Time{}
    }
    return c.connectedAt
}

func (c *Client) LastOKAt() time.Time {
    if c == nil {
        return time.Time{}
    }
    return c.lastOKAt
}

func (c *Client) TouchOK() {
    if c == nil {
        return
    }
    c.lastOKAt = time.Now()
}

// Конструктор по OAuth2 (XOAUTH2).
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

	now := time.Now()
	sessionID := fmt.Sprintf("%d", now.UnixNano())

	client := &Client{
		conn:        c,
		cfg:         cfg,
		email:       email,
		sessionID:   sessionID,
		connectedAt: now,
		lastOKAt:    now,
	}

	log.Printf("imap client ready | email=%s session_id=%s", email, sessionID)

	return client, nil
}

func (c *Client) FetchUnread() ([]imap.UID, error) {
    criteria := &imap.SearchCriteria{
        NotFlag: []imap.Flag{"\\Seen"},
    }

    started := time.Now()
    log.Printf(
        "imap search unread start | email=%s session_id=%s age=%s",
        c.email,
        c.sessionID,
        time.Since(c.connectedAt),
    )

    searchData, err := c.conn.UIDSearch(criteria, nil).Wait()
    duration := time.Since(started)
    if err != nil {
        return nil, fmt.Errorf(
            "search unread: session_id=%s duration=%s: %w",
            c.sessionID,
            duration,
            err,
        )
    }

    c.TouchOK()

    uids := searchData.AllUIDs()
    log.Printf(
        "imap search unread done | email=%s session_id=%s duration=%s count=%d uids=%v",
        c.email,
        c.sessionID,
        duration,
        len(uids),
        uids,
    )

    if len(uids) == 0 {
        c.logAllMessagesDiagnostic()
        return nil, nil
    }

    return uids, nil
}

func (c *Client) logAllMessagesDiagnostic() {
    started := time.Now()

    log.Printf(
        "imap diagnostic all start | email=%s session_id=%s age=%s",
        c.email,
        c.sessionID,
        time.Since(c.connectedAt),
    )

    allCriteria := &imap.SearchCriteria{}
    searchData, err := c.conn.UIDSearch(allCriteria, nil).Wait()
    duration := time.Since(started)
    if err != nil {
        log.Printf(
            "imap diagnostic all failed | email=%s session_id=%s duration=%s err=%v",
            c.email,
            c.sessionID,
            duration,
            err,
        )
        return
    }

    c.TouchOK()

    allUIDs := searchData.AllUIDs()
    log.Printf(
        "imap diagnostic all done | email=%s session_id=%s duration=%s count=%d",
        c.email,
        c.sessionID,
        duration,
        len(allUIDs),
    )

    if len(allUIDs) == 0 {
        log.Printf(
            "imap diagnostic all empty | email=%s session_id=%s",
            c.email,
            c.sessionID,
        )
        return
    }

    sorted := append([]imap.UID(nil), allUIDs...)
    sort.Slice(sorted, func(i, j int) bool { return sorted[i] < sorted[j] })

    limit := 5
    if len(sorted) < limit {
        limit = len(sorted)
    }

    tail := sorted[len(sorted)-limit:]
    log.Printf(
        "imap diagnostic recent uids | email=%s session_id=%s recent_uids=%v",
        c.email,
        c.sessionID,
        tail,
    )
}

func (c *Client) FetchMessage(uid imap.UID) (*imapclient.FetchCommand, error) {
	log.Printf("imap fetch message | email=%s session_id=%s uid=%d", c.email, c.sessionID, uid)

	fetchOptions := &imap.FetchOptions{
		UID:      true,
		Envelope: true,
		BodySection: []*imap.FetchItemBodySection{
            {
                Peek: true,
                Specifier: imap.PartSpecifierHeader,
            },
            {
                Peek: true,
            },
        },
	}

	c.TouchOK()
	return c.conn.Fetch(imap.UIDSetNum(uid), fetchOptions), nil
}

func (c *Client) MarkRead(uid imap.UID) error {
    started := time.Now()

    storeFlags := imap.StoreFlags{
        Op:    imap.StoreFlagsAdd,
        Flags: []imap.Flag{"\\Seen"},
    }

    log.Printf("imap mark read start | email=%s session_id=%s uid=%d", c.email, c.sessionID, uid)

    storeCmd := c.conn.Store(imap.UIDSetNum(uid), &storeFlags, nil)
    if err := storeCmd.Close(); err != nil {
        return fmt.Errorf("mark read uid=%d session_id=%s duration=%s: %w", uid, c.sessionID, time.Since(started), err)
    }

    c.TouchOK()
    log.Printf("imap mark read done | email=%s session_id=%s uid=%d duration=%s", c.email, c.sessionID, uid, time.Since(started))
    return nil
}

func (c *Client) Close() error {
    log.Printf("imap client close | email=%s session_id=%s age=%s last_ok_ago=%s",
        c.email,
        c.sessionID,
        time.Since(c.connectedAt),
        time.Since(c.lastOKAt),
    )
    return c.conn.Close()
}

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
