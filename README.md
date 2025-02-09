# StealerLogsDashboard

good looking dashboard to query your infostealer logs.

## Installation

1. **Clone the repository**

    ```bash
    git clone https://github.com/ayxkaddd/StealerLogsDashboard
    cd StealerLogsDashboard
    ```

2. **Create a virtual environment and activate it**

    ```bash
    python -m venv venv
    source venv/bin/activate
    ```

3. **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```
4. **Install PostgreSQl on your system. For example with docker-compose**:
    docker-compose.yml:
    ```yml
    version: "3.8"
    services:
    db:
        container_name: postgres_container
        image: postgres
        restart: always
        environment:
        POSTGRES_USER: root
        POSTGRES_PASSWORD: root
        POSTGRES_DB: test_db
        ports:
        - "5432:5432"
    ```
    Run:
    ```bash
    docker-compose up -d
    ```

---

## Configuration
1. **Configure the database**
   - Update `config.py`:
     ```python
     DATABASE_URL = "postgresql+asyncpg://root:root@localhost/stealer_logs"
     ```
2. **Configure Telegram API credentials**:
   - Update `config.py`:
     ```python
     API_ID = "your_api_id"
     API_HASH = "your_api_hash"
     ```
   - You can obtain these credentials by visiting my.telegram.org/auth?to=apps. Sign in to your Telegram account, create a new app or retrieve the credentials from an existing one.

---

## Usage
1. **Generate and Apply Migrations**:
    ```bash
    alembic revision --autogenerate -m "Initial migration"
    alembic upgrade head
    ```
2. **Start the Dashboard**:
    ```bash
    uvicorn main:app --reload
    ```
    By default, the app will be available at `http://127.0.0.1:8000`.
4. **Import Logs to database**:
    ```bash
    curl -X 'POST' 'http://127.0.0.1:8000/api/logs/import/?file_path=/path/to/your/log' -H 'accept: application/json'
    ```

---

## Preview

<p align="center"><img src="assets/2025-01-20_00-28.png"></p>
