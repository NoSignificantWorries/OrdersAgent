package parser

import (
    "fmt"
    "io"
    "strconv"
    "strings"
    "mime"
    "encoding/base64"
    "log"

    htmllib "golang.org/x/net/html"

    "github.com/emersion/go-imap/v2"
    "github.com/emersion/go-imap/v2/imapclient"
    "github.com/emersion/go-message/mail"
    "golang.org/x/text/encoding/charmap"
)

type Email struct {
    UID      imap.UID
    From     string
    Subject  string
    Date     string
    Body     string
    Files    []Attachment
}

type Attachment struct {
    Name string
    Data []byte
}

func decodeHeader(s string) string {
    if s == "" {
        return s
    }

    // 1. Стандартный декодер (работает для UTF-8)
    d := new(mime.WordDecoder)
    if decoded, err := d.DecodeHeader(s); err == nil && decoded != s {
        return decoded
    }

    // 2. Специальные кодировки
    if strings.Contains(s, "koi8-r") {
        return decodeKoi8R(s)
    }
    if strings.Contains(s, "windows-1251") {
        return decodeWindows1251(s)
    }

    return s
}

func decodeWindows1251(s string) string {
    parts := strings.Fields(s)
    var result []string

    for _, p := range parts {
        // B-кодировка
        if strings.HasPrefix(p, "=?windows-1251?B?") && strings.HasSuffix(p, "?=") {
            idxB := strings.Index(p, "?B?")
            if idxB == -1 {
                continue
            }
            data := p[idxB+3 : len(p)-2]
            decodedBytes, err := base64.StdEncoding.DecodeString(data)
            if err != nil {
                continue
            }
            decoded, err := charmap.Windows1251.NewDecoder().String(string(decodedBytes))
            if err == nil {
                result = append(result, decoded)
            }
            continue
        }

        // Q-кодировка
        if strings.HasPrefix(p, "=?windows-1251?Q?") && strings.HasSuffix(p, "?=") {
            idxQ := strings.Index(p, "?Q?")
            if idxQ == -1 {
                continue
            }
            data := p[idxQ+3 : len(p)-2]
            decodedBytes := decodeQuotedPrintable(data)
            decoded, err := charmap.Windows1251.NewDecoder().String(string(decodedBytes))
            if err == nil {
                result = append(result, decoded)
            }
            continue
        }
    }

    if len(result) > 0 {
        return strings.Join(result, " ")
    }
    return s
}


func decodeKoi8R(s string) string {
    parts := strings.Fields(s)
    var result []string

    for _, p := range parts {
        if !strings.HasPrefix(p, "=?koi8-r?B?") || !strings.HasSuffix(p, "?=") {
            continue
        }

        // Извлекаем base64 данные
        idxB := strings.Index(p, "?B?")
        if idxB == -1 {
            continue
        }
        data := p[idxB+3 : len(p)-2]

        decodedBytes, err := base64.StdEncoding.DecodeString(data)
        if err != nil {
            continue
        }

        // KOI8-R в UTF-8
        decoded, err := charmap.KOI8R.NewDecoder().String(string(decodedBytes))
        if err == nil {
            result = append(result, decoded)
        }
    }

    if len(result) > 0 {
        return strings.Join(result, " ")
    }
    return s
}

// Вспомогательная функция для Quoted-Printable
func decodeQuotedPrintable(s string) []byte {
    var result []byte
    i := 0
    for i < len(s) {
        if s[i] == '=' && i+2 < len(s) {
            if s[i+1] == '\r' && s[i+2] == '\n' {
                i += 3
                continue
            }
            hex := s[i+1 : i+3]
            if v, err := strconv.ParseUint("0x"+string(hex), 0, 8); err == nil {
                result = append(result, byte(v))
                i += 3
                continue
            }
        }
        result = append(result, s[i])
        i++
    }
    return result
}


func ParseMessage(uid imap.UID, fetchCmd *imapclient.FetchCommand) (*Email, error) {
    msg := fetchCmd.Next()
    if msg == nil {
        return nil, fmt.Errorf("no message")
    }

    email := &Email{
        UID: uid,
    }

    var bodyError error

    for {
        item := msg.Next()
        if item == nil {
            break
        }

        // 1. Заголовки
        if env, ok := item.(imapclient.FetchItemDataEnvelope); ok {
            decSubject := decodeHeader(env.Envelope.Subject)

            email.Subject = decSubject
            email.From = ""

            for _, addr := range env.Envelope.From {
                decodedName := decodeHeader(addr.Name)

                if len(decodedName) > 0 {
                    email.From += decodedName + " "
                }
                if len(addr.Mailbox) > 0 && len(addr.Host) > 0 {
                    email.From += fmt.Sprintf("<%s@%s> ", addr.Mailbox, addr.Host)
                }
            }

            if !env.Envelope.Date.IsZero() {
                email.Date = env.Envelope.Date.Format("2006-01-02 15:04")
            }

            continue
        }

        // 2. Тело письма
        if bodyData, ok := item.(imapclient.FetchItemDataBodySection); ok && bodyData.Literal != nil {
            if err := parseBody(email, bodyData.Literal); err != nil {
                bodyError = err
            }
            continue
        }
    }

    return email, bodyError
}

func cleanBodyText(body string) string {
    // Сначала вычищаем рамки forwarded прямо в тексте,
    // а не выкидываем строки целиком.
    replacements := []string{
        "-------- Пересылаемое сообщение --------",
        "-------- Пересылаемое письмо --------",
        "-------- Конец пересылаемого сообщения --------",
        "-------- Конец пересылаемого письма --------",
    }
    for _, r := range replacements {
        body = strings.ReplaceAll(body, r, "")
    }

    lines := strings.Split(body, "\n")
    var cleaned []string

    // важно: итерируемся по значениям, а не по индексам
    for _, raw := range lines {
        line := strings.TrimSpace(raw)

        if line == "" {
            continue
        }

        // Служебные строки пересылки
        if strings.HasPrefix(line, "От:") ||
            strings.HasPrefix(line, "К:") ||
            strings.HasPrefix(line, "Кому:") ||
            strings.HasPrefix(line, "А также к:") ||
            strings.HasPrefix(line, "Тема:") ||
            strings.HasPrefix(line, "Дата:") ||
            strings.HasPrefix(line, "Время создания:") ||
            strings.HasPrefix(line, "Прикрепленные файлы:") {
            continue
        }

        // HTML/CSS‑мусор
        if strings.Contains(line, "blockquote.rt") ||
            strings.HasPrefix(line, "p {") ||
            strings.Contains(line, ".email-signature") {
            continue
        }

        if strings.HasPrefix(line, "С уважением") ||
            line == "--" {
            break
        }

        cleaned = append(cleaned, line)
    }

    result := strings.Join(cleaned, "\n")
    return result
}

func parseBody(email *Email, literal io.Reader) error {
    mr, err := mail.CreateReader(literal)
    if err != nil {
        return fmt.Errorf("parsing body: %w", err)
    }

    var parts []string

    for {
        p, err := mr.NextPart()
        if err == io.EOF {
            break
        }
        if err != nil {
            continue
        }

        contentType := p.Header.Get("Content-Type")
        
        // text/plain
        if strings.HasPrefix(contentType, "text/plain") {
            bodyBytes, _ := io.ReadAll(p.Body)
            txt := strings.TrimSpace(string(bodyBytes))
            if txt != "" {
                parts = append(parts, txt)
            }
            continue
        }

        // text/html
        if strings.HasPrefix(contentType, "text/html") {
            bodyBytes, _ := io.ReadAll(p.Body)
            txt := strings.TrimSpace(extractTextFromHTML(string(bodyBytes)))
            if txt != "" {
                parts = append(parts, txt)
            }
            continue
        }

        // 3. Вложенное письмо message/rfc822 (типично для Fwd:)
        if strings.HasPrefix(contentType, "message/rfc822") {
            nestedRaw, _ := io.ReadAll(p.Body)
            // Простой способ: вытащить текст как из HTML
            nestedText := strings.TrimSpace(extractTextFromHTML(string(nestedRaw)))
            if nestedText != "" {
                parts = append(parts, nestedText)
            }
            // Более продвинутый вариант — создать новый mail.Reader
            // и пройтись по нему так же, как по основному письму.
            continue
        }

        // Вложения
        disposition := p.Header.Get("Content-Disposition")
        if strings.Contains(disposition, "attachment") ||
           strings.HasPrefix(contentType, "application/") ||
           strings.HasPrefix(contentType, "image/") {
            
            name := extractFilename(disposition, contentType)
            if name == "" {
                continue
            }

            att := Attachment{
                Name: name,
            }
            att.Data, _ = io.ReadAll(p.Body)
            email.Files = append(email.Files, att)
        }
    }

    log.Printf("parseBody: UID=%d parts before clean: %d", email.UID, len(parts))

    email.Body = strings.Join(parts, "\n\n")
    email.Body = cleanBodyText(email.Body)
    return nil
}

// чистый текст из HTML
func extractTextFromHTML(htmlStr string) string {
    doc, err := htmllib.Parse(strings.NewReader(htmlStr))
    if err != nil {
        return htmlStr
    }

    var text strings.Builder
    var f func(*htmllib.Node)
    f = func(n *htmllib.Node) {
        if n.Type == htmllib.TextNode {
            text.WriteString(strings.TrimSpace(n.Data) + " ")
        }
        for c := n.FirstChild; c != nil; c = c.NextSibling {
            f(c)
        }
    }
    f(doc)
    
    result := text.String()
    
    result = strings.Join(strings.Fields(result), " ")
    return result
}

func extractFilename(disposition, contentType string) string {
    var filename string

    if idx := strings.Index(disposition, "filename="); idx >= 0 {
        rawFilename := disposition[idx+9:]
        rawFilename = strings.Trim(rawFilename, "\"")

        filename = decodeHeader(rawFilename)
    }

    // Если имени нет  это мусорное вложение (подпись и т.п.)
    if filename == "" {
        return ""
    }

    // Очистка опасных символов
    filename = strings.Map(func(r rune) rune {
        switch r {
        case '/', '\\', ':', '*', '?', '"', '<', '>', '|':
            return '_'
        }
        return r
    }, filename)

    return filename
}

