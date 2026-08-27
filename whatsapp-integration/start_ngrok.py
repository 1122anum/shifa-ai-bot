"""
start_ngrok.py — ngrok tunnel starter.

Usage:
    python start_ngrok.py

Tunnel tab tak chalta rahega jab tak Ctrl+C na dabao.
Auth token is read from .env (NGROK_AUTH_TOKEN) — never hardcoded.
"""

from pyngrok import ngrok, conf, process
import re, os, time
from dotenv import load_dotenv

load_dotenv()

PORT = 5000


def update_env(url: str) -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    content = open(env_path).read()
    if "NGROK_PUBLIC_URL=" in content:
        content = re.sub(r"NGROK_PUBLIC_URL=.*", f"NGROK_PUBLIC_URL={url}", content)
    else:
        content += f"\nNGROK_PUBLIC_URL={url}\n"
    open(env_path, "w").write(content)


def main() -> None:
    print("=" * 55)
    print("   Shifa AI — ngrok Tunnel")
    print("=" * 55)

    # Read token from environment — never hardcode
    auth_token = os.getenv("NGROK_AUTH_TOKEN", "")
    if not auth_token:
        print("\n  ERROR: NGROK_AUTH_TOKEN not set in .env")
        print("  Add: NGROK_AUTH_TOKEN=your_token  to .env")
        print("  Get token: https://dashboard.ngrok.com/get-started/your-authtoken")
        return

    # Kill any old processes
    try:
        process._current_processes.clear()
        ngrok.kill()
    except Exception:
        pass

    # Configure token
    conf.get_default().auth_token = auth_token
    print(f"\n  Auth token loaded from .env")
    print(f"  Starting tunnel on port {PORT}...")

    try:
        tunnel = ngrok.connect(PORT, "http", pooling_enabled=True)
        url = tunnel.public_url.replace("http://", "https://")

        print(f"\n  Tunnel LIVE!")
        print(f"\n  Public URL : {url}")
        print(f"  Webhook    : {url}/webhook/whatsapp")
        print(f"  Health     : {url}/health")
        print("\n" + "=" * 55)
        print(f"  Meta Console mein ye daalo:")
        print(f"  Callback URL : {url}/webhook/whatsapp")
        print(f"  Verify Token : shifa_verify_token")
        print("=" * 55)

        update_env(url)
        print(f"\n  .env updated!")
        print(f"  Tunnel chal raha hai... Ctrl+C se band karo\n")

        # Keep alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n  Tunnel band ho gaya.")
        ngrok.kill()
    except Exception as exc:
        print(f"\n  Error: {exc}")


if __name__ == "__main__":
    main()
