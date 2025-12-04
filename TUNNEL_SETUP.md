# Настройка постоянного Cloudflare Tunnel

## Шаги на сайте Cloudflare Zero Trust:

1. Зайди на https://one.dash.cloudflare.com/
2. Войди в аккаунт
3. Перейди в **Networks** → **Tunnels**
4. Нажми **"Create a tunnel"**
5. Выбери **"Cloudflared"** → **Next**
6. Введи имя: `hvac-news-backend`
7. Нажми **"Save tunnel"**

## После создания туннеля:

На экране будет показана команда для запуска, например:
```
cloudflared tunnel run hvac-news-backend
```

Или нужно будет настроить конфигурацию.

## Настройка маршрутизации:

После создания туннеля нужно добавить Public Hostname:
1. В настройках туннеля нажми **"Configure"**
2. Перейди на вкладку **"Public Hostnames"**
3. Нажми **"Add a public hostname"**
4. Заполни:
   - **Subdomain**: `hvac-news` (или любое другое имя)
   - **Domain**: выбери `trycloudflare.com` из списка
   - **Service**: `http://127.0.0.1:8000`
5. Нажми **"Save hostname"**

После этого у тебя будет постоянный URL: `https://hvac-news.trycloudflare.com`

## Запуск туннеля локально:

После настройки запусти туннель командой:
```bash
cloudflared tunnel run hvac-news-backend
```

Туннель будет работать постоянно, пока процесс запущен.

