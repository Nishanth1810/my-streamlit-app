import streamlit as st
import pandas as pd
import requests
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
import gspread
from bs4 import BeautifulSoup
from wordpress_xmlrpc import Client, WordPressPost
from wordpress_xmlrpc.methods.posts import NewPost
from wordpress_xmlrpc.methods.media import UploadFile
from wordpress_xmlrpc.compat import xmlrpc_client

# --- Configuration ---
CREDENTIALS_FILE = 'evident-bedrock-464104-k8-3b568bdf291a.json'
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

SHEETS = [
    {
        "url": "https://docs.google.com/spreadsheets/d/1_JHanBj9Y8q5bfrNG61PXp6reinkqNSkyhdt21G4b80/edit#gid=0",
        "sheet_name": "Sheet1",
        "wp_site": "https://amcounsellingservices.ca/xmlrpc.php",
        "wp_user": "SEO-Team",
        "wp_app_password": "k7MP oN5O SdDL S2IF Edie kPaX"
    }
]

# --- Helper Functions ---
def clean_html(raw_html):
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup.find_all("style"):
        tag.decompose()
    for tag in soup.find_all(True):
        tag.attrs = {key: val for key, val in tag.attrs.items() if key not in ['style', 'class', 'id']}
    return str(soup)

def extract_title_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    return h1.get_text().strip() if h1 else "Untitled Post"

def get_doc_content(doc_url, session, creds):
    try:
        doc_id = doc_url.split("/d/")[1].split("/")[0]
        creds.refresh(Request())
        export_url = f"https://docs.google.com/feeds/download/documents/export/Export?id={doc_id}&exportFormat=html"
        headers = {'Authorization': f'Bearer {creds.token}'}
        response = session.get(export_url, headers=headers)
        if response.status_code == 200:
            return clean_html(response.text)
        else:
            return ''
    except Exception as e:
        return ''

def upload_image(image_url, wp_client):
    try:
        r = requests.get(image_url)
        if r.status_code != 200:
            return None
        data = {
            'name': 'image.jpg',
            'type': 'image/jpeg',
            'bits': xmlrpc_client.Binary(r.content),
            'overwrite': True
        }
        media = wp_client.call(UploadFile(data))
        return media['id']
    except:
        return None

def post_to_wordpress(wp_client, title, content, slug, status, meta_title, meta_description, category_id, featured_image_id=None):
    post = WordPressPost()
    post.title = title
    post.slug = slug
    post.content = content
    post.post_status = status
    if category_id:
        post.terms_names = {'category': [category_id]}
    post.custom_fields = [
        {'key': 'meta_title', 'value': meta_title},
        {'key': 'meta_description', 'value': meta_description},
    ]
    if featured_image_id:
        post.thumbnail = featured_image_id
    wp_client.call(NewPost(post))

# --- Streamlit UI ---
st.title("📤 Blog Auto Publisher")

if st.button("Publish All Blogs"):
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    creds.refresh(Request())
    gc = gspread.authorize(creds)
    session = requests.Session()

    for site in SHEETS:
        st.subheader(f"Processing: {site['sheet_name']}")
        try:
            sheet_id = site["url"].split("/d/")[1].split("/")[0]
            worksheet = gc.open_by_key(sheet_id).worksheet(site["sheet_name"])
            df = pd.DataFrame(worksheet.get_all_records())
            required = {'slug', 'status', 'meta_title', 'meta_description', 'category_id', 'content_doc_url'}
            if not required.issubset(df.columns):
                st.error(f"Missing required columns: {required - set(df.columns)}")
                continue

            wp_client = Client(site["wp_site"], site["wp_user"], site["wp_app_password"])

            for i, row in df.iterrows():
                with st.expander(f"Post {i+2} - {row.get('slug', 'Untitled')}"):
                    html = get_doc_content(row['content_doc_url'], session, creds)
                    if not html:
                        st.warning("Skipped: No content")
                        continue

                    title = extract_title_from_html(html)
                    slug = row['slug'] if row['slug'] else title.lower().replace(' ', '-')
                    image_id = upload_image(row.get('featured_image_url', ''), wp_client) if 'featured_image_url' in row else None

                    post_to_wordpress(
                        wp_client, title, html, slug, row['status'],
                        row['meta_title'], row['meta_description'], row['category_id'], image_id
                    )
                    st.success(f"✅ Posted: {title}")

        except Exception as e:
            st.error(f"❌ Error: {e}")
