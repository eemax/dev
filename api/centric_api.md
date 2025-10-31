# Instructions for Centric API
```
touch .env
```
```
[centric_api]
base_url=https://nwg-prod.centricsoftware.com
username=your_username
password=your_password
default_endpoint=v2/styles
```

### Usage

```
# Using .env defaults (writes to payload.json by default)
./centric_api.py -e v2/materials
```

### Flags

```
-b, --base-url URL     Base URL (e.g. https://nwg-prod.centricsoftware.com)
-u, --username USER    Username
-p, --password PASS    Password
-e, --endpoint PATH    Versioned endpoint (e.g. v2/materials, v3/styles)
-m, --method METHOD    HTTP method (default: GET)
-d, --data DATA        JSON body or @file.json for non-GET requests
-o, --out FILE         Write response to file (default: payload.json)
    --raw              Do not pretty print JSON; write raw response
    --token-only       Print only the token and exit
    --env-file PATH    Path to .env file (default: ./api/.env)
    --token TOKEN      Use an explicit token (skip authentication)
    --token-file PATH  Path to token cache file (default: ./api/.token)
    --timeout SECONDS  HTTP timeout in seconds (default: 30)
```

### Notes

- Output is pretty-printed JSON by default unless `--raw` is used.
- If `--token` is not provided, the script will read a cached token from `--token-file` if it exists. On 401 responses, it will re-authenticate, update the token file, and retry once.