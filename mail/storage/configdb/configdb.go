package configdb

import (
    "os"
    "strconv"
)

type Config struct {
    Host     string
    Port     int
    User     string
    Password string
    Name     string
}

func FromEnv() *Config {
    host := os.Getenv("POSTGRES_HOST")
    if host == "" {
        host = "localhost"
    }

    port := 5432
    if p := os.Getenv("POSTGRES_PORT"); p != "" {
        if v, err := strconv.Atoi(p); err == nil {
            port = v
        }
    }

    return &Config{
        Host:     host,
        Port:     port,
        User:     os.Getenv("POSTGRES_USER"),
        Password: os.Getenv("POSTGRES_PASSWORD"),
        Name:     os.Getenv("POSTGRES_DB"),
    }
}
