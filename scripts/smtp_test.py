import smtplib
import sys

def test_office365_smtp():
    # Configuration for Office 365
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    
    # CREDENTIALS
    smtp_user = "sales@apptor.io"  # <--- CHANGE THIS
    smtp_password = "J*609499667245ox"   # <--- CHANGE THIS

    print(f"Attempting to connect to {smtp_server}:{smtp_port}...")

    try:
        # 1. Initialize the connection
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.set_debuglevel(1) # Prints detailed interaction logs to console
        
        # 2. Identify yourself to the server
        server.ehlo()
        
        # 3. Secure the connection (Required for O365)
        if server.has_extn('STARTTLS'):
            print("Starting TLS...")
            server.starttls()
            server.ehlo() # Re-identify after TLS start
        
        # 4. Attempt Login
        print(f"Attempting login for user: {smtp_user}")
        server.login(smtp_user, smtp_password)
        
        print("\n--------------------------------------------------")
        print("SUCCESS: Authentication accepted.")
        print("The user is authorized to send via SMTP.")
        print("--------------------------------------------------")
        
        server.quit()

    except smtplib.SMTPAuthenticationError as e:
        print("\n--------------------------------------------------")
        print("FAILED: Authentication Error.")
        print(f"Error Code: {e.smtp_code}")
        print(f"Error Message: {e.smtp_error}")
        print("--------------------------------------------------")
        print("DIAGNOSIS: If the code is still 535 5.7.139, the Admin 'Authenticated SMTP' setting has not propagated yet, or Azure Security Defaults are blocking it.")
        
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")

if __name__ == "__main__":
    test_office365_smtp()