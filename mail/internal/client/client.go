package client

import (
	"fmt"
	"log"
	"sort"
	"time"

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
	uidValidity uint32
	uidNext     imap.UID
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

func (c *Client) UIDValidity() uint32 {
	if c == nil {
		return 0
	}
	return c.uidValidity
}

// UIDNextAtConnect возвращает UIDNEXT на момент выбора INBOX
// При подключении, а не постоянно обновляемое значение
func (c *Client) UIDNextAtConnect() imap.UID {
	if c == nil {
		return 0
	}
	return c.uidNext
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

	selected, err := c.Select("INBOX", nil).Wait()
	if err != nil {
		_ = c.Close()
		return nil, fmt.Errorf("select INBOX: %w", err)
	}

	if selected.UIDValidity == 0 {
		_ = c.Close()
		return nil, fmt.Errorf(
			"select INBOX: server returned invalid UIDVALIDITY=0",
		)
	}

	if selected.UIDNext == 0 {
		_ = c.Close()
		return nil, fmt.Errorf(
			"select INBOX: server did not provide a usable UIDNEXT",
		)
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
		uidValidity: selected.UIDValidity,
		uidNext:     selected.UIDNext,
	}

	log.Printf(
		"imap client ready | email=%s session_id=%s uid_validity=%d uid_next=%d",
		email,
		sessionID,
		client.uidValidity,
		client.uidNext,
	)

	return client, nil
}

// InboxSyncBoundary получает свежие данные INBOX для восстановления
func (c *Client) InboxSyncBoundary() (
	uidValidity uint32,
	uidNext imap.UID,
	err error,
) {
	started := time.Now()

	status, err := c.conn.Status(
		"INBOX",
		&imap.StatusOptions{
			UIDValidity: true,
			UIDNext:     true,
		},
	).Wait()
	if err != nil {
		return 0, 0, fmt.Errorf(
			"status INBOX: session_id=%s duration=%s: %w",
			c.sessionID,
			time.Since(started),
			err,
		)
	}

	if status.UIDValidity == 0 || status.UIDNext == 0 {
		return 0, 0, fmt.Errorf(
			"status INBOX returned invalid sync data: session_id=%s uid_validity=%d uid_next=%d",
			c.sessionID,
			status.UIDValidity,
			status.UIDNext,
		)
	}

	if status.UIDValidity != c.uidValidity {
		return 0, 0, fmt.Errorf(
			"UIDVALIDITY changed during session: session_id=%s selected=%d current=%d; reconnect required",
			c.sessionID,
			c.uidValidity,
			status.UIDValidity,
		)
	}

	c.TouchOK()

	log.Printf(
		"imap sync boundary | email=%s session_id=%s uid_validity=%d uid_next=%d duration=%s",
		c.email,
		c.sessionID,
		status.UIDValidity,
		status.UIDNext,
		time.Since(started),
	)

	return status.UIDValidity, status.UIDNext, nil
}

// SearchUIDRange возвращает существующие UID в замкнутом диапазоне.
// Статус прочтения не учитывается.
// Тела писем не скачиваются.
func (c *Client) SearchUIDRange(
	first imap.UID,
	last imap.UID,
) ([]imap.UID, error) {
	if first == 0 || last == 0 {
		return nil, fmt.Errorf(
			"invalid UID range: first=%d last=%d; zero is not allowed",
			first,
			last,
		)
	}

	if first > last {
		return nil, fmt.Errorf(
			"invalid UID range: first=%d exceeds last=%d",
			first,
			last,
		)
	}

	var uidSet imap.UIDSet
	uidSet.AddRange(first, last)

	criteria := &imap.SearchCriteria{
		UID: []imap.UIDSet{uidSet},
	}

	started := time.Now()

	log.Printf(
		"imap sync search start | email=%s session_id=%s first_uid=%d last_uid=%d",
		c.email,
		c.sessionID,
		first,
		last,
	)

	searchData, err := c.conn.UIDSearch(criteria, nil).Wait()
	if err != nil {
		return nil, fmt.Errorf(
			"search UID range %d:%d: session_id=%s duration=%s: %w",
			first,
			last,
			c.sessionID,
			time.Since(started),
			err,
		)
	}

	uids := searchData.AllUIDs()

	for _, uid := range uids {
		if uid < first || uid > last {
			return nil, fmt.Errorf(
				"search UID range returned out-of-range UID: session_id=%s requested=%d:%d received=%d",
				c.sessionID,
				first,
				last,
				uid,
			)
		}
	}

	sort.Slice(uids, func(i, j int) bool {
		return uids[i] < uids[j]
	})

	c.TouchOK()

	log.Printf(
		"imap sync search done | email=%s session_id=%s first_uid=%d last_uid=%d count=%d duration=%s",
		c.email,
		c.sessionID,
		first,
		last,
		len(uids),
		time.Since(started),
	)

	return uids, nil
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
		//c.logAllMessagesDiagnostic()
		return nil, nil
	}

	return uids, nil
}

func (c *Client) FetchMessage(uid imap.UID) (*imapclient.FetchCommand, error) {
	log.Printf("imap fetch message | email=%s session_id=%s uid=%d", c.email, c.sessionID, uid)

	fetchOptions := &imap.FetchOptions{
		UID:      true,
		Envelope: true,
		BodySection: []*imap.FetchItemBodySection{
			{
				Peek:      true,
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
