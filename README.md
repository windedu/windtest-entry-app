# WindTest Entry App

This is a standalone Streamlit application for entering math test scores into Notion.

## Deployment to Streamlit Cloud (Recommended)

1.  **Push to GitHub**:
    *   Initialize a git repository in this folder (or pushing the parent folder is fine too).
    *   Commit `entry_app.py`, `requirements.txt`, and `.gitignore`.
    *   **Do NOT commit `.streamlit/secrets.toml`** (it is gitignored).
    *   Push to GitHub.

2.  **Deploy**:
    *   Go to [share.streamlit.io](https://share.streamlit.io/).
    *   Click "New app".
    *   Select your repository and branch.
    *   Main file path: `entry_app.py`.
    *   Click **Advanced Settings** -> **Secrets**.
    *   Paste the contents of your local `.streamlit/secrets.toml` into the secrets area:
        ```toml
        NOTION_TOKEN = "your_token_here"
        STUDENT_DB_ID = "..."
        Q_DB_ID = "..."
        R_DB_ID = "..."
        REPORT_DB_ID = "..."
        ADMIN_USER_ID = "..."
        ```
    *   Click **Deploy**.

## Local Development

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Run the app:
    ```bash
    streamlit run entry_app.py
    ```
    *The app will automatically read `NOTION_TOKEN` etc. from `.streamlit/secrets.toml`.*
