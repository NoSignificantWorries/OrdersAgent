package config

import (
    "encoding/json"
    "fmt"
    "os"
)

type Config struct {
    Host     string `json:"host"`
    Port     int    `json:"port"`
    Username string `json:"username"`
    Password string `json:"password"`
}

func Load(filename string) (*Config, error) {
    data, err := os.ReadFile(filename)
    if err != nil {
        return nil, fmt.Errorf("config.json не найден: %w", err)
    }
    
    var cfg Config
    if err := json.Unmarshal(data, &cfg); err != nil {
        return nil, fmt.Errorf("неверный config.json: %w", err)
    }
    return &cfg, nil
}
