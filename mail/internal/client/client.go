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

func New(cfg *config.Config) (*Client, error) {
    c, err := imapclient.DialTLS(cfg.Host+":"+fmt.Sprintf("%d", cfg.Port), nil)
    if err != nil {
        return nil, fmt.Errorf("dial: %w", err)
    }
    
    if err := c.Login(cfg.Username, cfg.Password).Wait(); err != nil {
        c.Close()
        return nil, fmt.Errorf("login: %w", err)
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
   
    // флаги для определения непрочитанных
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
   
    fmt.Printf("Total: %d, Unread: %d\n", len(allUIDs), len(unreadUIDs))
    return unreadUIDs, nil
}

func (c *Client) FetchMessage(uid imap.UID) (*imapclient.FetchCommand, error) {
    fetchOptions := &imap.FetchOptions{
        UID:        true,
        Envelope:   true,
        BodySection: []*imap.FetchItemBodySection{{
            Peek: true,
        }},
    }
    
    return c.conn.Fetch(imap.UIDSetNum(uid), fetchOptions), nil
}

func (c *Client) MarkRead(uid imap.UID) error {
    storeFlags := imap.StoreFlags{
        Op:     imap.StoreFlagsAdd,
        Flags:  []imap.Flag{"\\Seen"},
        Silent: false,
    }
    storeCmd := c.conn.Store(imap.UIDSetNum(uid), &storeFlags, nil)
    return storeCmd.Close()
}

func (c *Client) Close() error {
    return c.conn.Close()
}
