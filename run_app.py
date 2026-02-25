import sys

def main():
    # Equivalent to: streamlit run app_ui.py
    from streamlit.web import cli as stcli
    sys.argv = [
        "streamlit",
        "run",
        "app_ui.py",
        # 如果要局域网分享，打开下面两行：
        # "--server.address", "0.0.0.0",
        # "--server.port", "8501",
    ]
    sys.exit(stcli.main())

if __name__ == "__main__":
    main()