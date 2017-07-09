import smtplib, logging, io, config
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart

def email_alert(detail='(something needs your attention)', subject='Puffs Experiment Alert', figure=None):
    """Send an email

    detail : text of email
    subject : subject of email
    figure : (matplotlib fig instance,lock_for_fig)
    """
    from_addr = 'bensondaledexperiments@gmail.com'
    to_addr = config.email

    if to_addr is None:
        return

    msg = MIMEMultipart()

    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = to_addr

    text = MIMEText(detail)
    msg.attach(text)

    if figure is not None:
        fig,lock = figure
        with io.BytesIO() as buf, lock:
            fig.savefig(buf, format='png')
            buf.seek(0)
            image = MIMEImage(buf.read(-1), _subtype='png', name='figure.png')
        msg.attach(image)

    try:
        smtpserver = smtplib.SMTP("smtp.gmail.com", 587)
        smtpserver.ehlo()
        smtpserver.starttls()
        smtpserver.ehlo()
        smtpserver.login('bensondaledexperiments@gmail.com', 'experiment')
        smtpserver.sendmail(from_addr, to_addr, msg.as_string())
        smtpserver.close()
    except:
        logging.error('Email failed to send.')
