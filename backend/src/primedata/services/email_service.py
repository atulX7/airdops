"""
Email service for sending verification and notification emails.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from urllib.parse import quote
from loguru import logger

from primedata.core.settings import get_settings


def send_verification_email(email: str, verification_token: str, user_name: str = None) -> bool:
    """
    Send email verification email to user.
    
    Args:
        email: User's email address
        verification_token: Unique verification token
        user_name: Optional user's name for personalization
        
    Returns:
        True if email sent successfully, False otherwise
    """
    settings = get_settings()
    
    # Check if email is enabled
    if not settings.SMTP_ENABLED:
        logger.warning("SMTP is disabled. Email verification email not sent.")
        return False
    
    try:
        # Get frontend URL for verification link
        frontend_url = settings.FRONTEND_URL.rstrip('/')
        # URL-encode the token to handle special characters safely
        verification_link = f"{frontend_url}/verify-email?token={quote(verification_token)}"
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Verify your AIRDops account"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = email
        
        # Email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">AIRDops</h1>
            </div>
            <div class="content">
                <h2>Verify your email address</h2>
                <p>Hello{f' {user_name}' if user_name else ''},</p>
                <p>Thank you for signing up for AIRDops! Please verify your email address by clicking the button below:</p>
                <p style="text-align: center;">
                    <a href="{verification_link}" class="button">Verify Email Address</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{verification_link}</p>
                <p>This link will expire in 24 hours.</p>
                <p>If you didn't create an account with AIRDops, please ignore this email.</p>
                <div class="footer">
                    <p>© {settings.FRONTEND_URL.split('//')[-1].split('/')[0]} AIRDops. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        Verify your AIRDops account
        
        Hello{f' {user_name}' if user_name else ''},
        
        Thank you for signing up for AIRDops! Please verify your email address by visiting:
        
        {verification_link}
        
        This link will expire in 24 hours.
        
        If you didn't create an account with AIRDops, please ignore this email.
        """
        
        # Attach parts
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
        elif settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Verification email sent successfully to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send verification email to {email}: {str(e)}")
        return False


def send_password_reset_email(email: str, reset_token: str, user_name: str = None) -> bool:
    """
    Send password reset email to user.
    
    Args:
        email: User's email address
        reset_token: Unique reset token
        user_name: Optional user's name for personalization
        
    Returns:
        True if email sent successfully, False otherwise
    """
    settings = get_settings()
    
    if not settings.SMTP_ENABLED:
        logger.warning("SMTP is disabled. Password reset email not sent.")
        return False
    
    try:
        frontend_url = settings.FRONTEND_URL.rstrip('/')
        # URL-encode the token to handle special characters safely
        reset_link = f"{frontend_url}/reset-password?token={quote(reset_token)}"
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Reset your AIRDops password"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = email
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">AIRDops</h1>
            </div>
            <div class="content">
                <h2>Reset your password</h2>
                <p>Hello{f' {user_name}' if user_name else ''},</p>
                <p>You requested to reset your password. Click the button below to reset it:</p>
                <p style="text-align: center;">
                    <a href="{reset_link}" class="button">Reset Password</a>
                </p>
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; color: #667eea;">{reset_link}</p>
                <p>This link will expire in 1 hour.</p>
                <p>If you didn't request a password reset, please ignore this email.</p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Reset your AIRDops password
        
        Hello{f' {user_name}' if user_name else ''},
        
        You requested to reset your password. Visit:
        
        {reset_link}
        
        This link will expire in 1 hour.
        
        If you didn't request a password reset, please ignore this email.
        """
        
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
        elif settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Password reset email sent successfully to {email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}: {str(e)}")
        return False


def send_contact_email(user_name: str, user_email: str, feedback: str) -> bool:
    """
    Send contact form submission email to feedback address.
    
    Args:
        user_name: User's name
        user_email: User's email address
        feedback: User's feedback/query message
        
    Returns:
        True if email sent successfully, False otherwise
    """
    settings = get_settings()
    
    if not settings.SMTP_ENABLED:
        logger.warning("SMTP is disabled. Contact form email not sent.")
        return False
    
    try:
        # Feedback recipient email - use SMTP_TO_EMAIL setting or fallback to SMTP_USERNAME
        # ⚠️ WARNING: Set SMTP_TO_EMAIL environment variable for production!
        from primedata.core.settings import get_settings
        settings = get_settings()
        feedback_email = settings.SMTP_TO_EMAIL or settings.SMTP_USERNAME
        if not feedback_email:
            logger.error("SMTP_TO_EMAIL or SMTP_USERNAME must be set for contact form submissions")
            return False
        
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Contact Form Submission from {user_name}"
        msg['From'] = settings.SMTP_FROM_EMAIL
        msg['To'] = feedback_email
        msg['Reply-To'] = user_email  # Set reply-to to user's email
        
        # Email body (HTML)
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    padding: 30px;
                    border-radius: 10px;
                    color: white;
                }}
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    margin-top: 20px;
                    color: #333;
                }}
                .info-box {{
                    background: #f5f5f5;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 15px 0;
                    border-left: 4px solid #667eea;
                }}
                .feedback-box {{
                    background: #f9f9f9;
                    padding: 20px;
                    border-radius: 5px;
                    margin: 15px 0;
                    border: 1px solid #e0e0e0;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #eee;
                    font-size: 12px;
                    color: #666;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 style="margin: 0; color: white;">AIRDops Contact Form</h1>
            </div>
            <div class="content">
                <h2>New Contact Form Submission</h2>
                
                <div class="info-box">
                    <p><strong>Name:</strong> {user_name}</p>
                    <p><strong>Email:</strong> <a href="mailto:{user_email}">{user_email}</a></p>
                </div>
                
                <h3>Message:</h3>
                <div class="feedback-box">
                    {feedback}
                </div>
                
                <div class="footer">
                    <p>This email was sent from the AIRDops contact form.</p>
                    <p>You can reply directly to this email to respond to {user_name}.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_body = f"""
        AIRDops Contact Form Submission
        
        Name: {user_name}
        Email: {user_email}
        
        Message:
        {feedback}
        
        ---
        This email was sent from the AIRDops contact form.
        You can reply directly to this email to respond to {user_name}.
        """
        
        # Attach parts
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
            server.starttls()
        elif settings.SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        
        logger.info(f"Contact form email sent successfully from {user_name} ({user_email})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send contact form email from {user_email}: {str(e)}")
        return False
