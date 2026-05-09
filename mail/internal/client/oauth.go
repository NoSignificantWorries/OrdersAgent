package client

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"time"
)

type RefreshedToken struct {
	AccessToken     string
	RefreshToken    string
	AccessExpiresAt time.Time
}

type yandexTokenResponse struct {
	AccessToken string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn   int    `json:"expires_in"`
	TokenType   string `json:"token_type"`
	Error       string `json:"error"`
	ErrorDesc   string `json:"error_description"`
}

func RefreshYandexToken(tokenURL, clientID, clientSecret, refreshToken string) (*RefreshedToken, error) {
	form := url.Values{}
	form.Set("grant_type", "refresh_token")
	form.Set("refresh_token", refreshToken)
	form.Set("client_id", clientID)
	form.Set("client_secret", clientSecret)

	resp, err := http.Post(
		tokenURL,
		"application/x-www-form-urlencoded",
		bytes.NewBufferString(form.Encode()),
	)
	if err != nil {
		return nil, fmt.Errorf("post refresh token: %w", err)
	}
	defer resp.Body.Close()

	var tokenResp yandexTokenResponse
	if err := json.NewDecoder(resp.Body).Decode(&tokenResp); err != nil {
		return nil, fmt.Errorf("decode refresh response: %w", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("refresh token failed: status=%d error=%s description=%s",
			resp.StatusCode, tokenResp.Error, tokenResp.ErrorDesc)
	}

	if tokenResp.AccessToken == "" {
		return nil, fmt.Errorf("refresh token failed: empty access_token")
	}

	newRefresh := refreshToken
	if tokenResp.RefreshToken != "" {
		newRefresh = tokenResp.RefreshToken
	}

	return &RefreshedToken{
		AccessToken:     tokenResp.AccessToken,
		RefreshToken:    newRefresh,
		AccessExpiresAt: time.Now().Add(time.Duration(tokenResp.ExpiresIn) * time.Second),
	}, nil
}