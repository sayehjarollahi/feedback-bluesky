import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
from datetime import datetime
import uuid
import json
import time
import os
import random
from dotenv import load_dotenv

# Load the .env file
load_dotenv()
st.markdown(
    """
    <style>
    /* Background */
    html, body, .stApp, .main, .block-container {
        background-color: rgba(173, 216, 230, 0.08) !important;
    }

    /* ONLY Streamlit markdown text (fix white text) */
    .stMarkdown p,
    .stMarkdown li {
        color: #000000 !important;
    }

    /* Markdown headings (like "Welcome to Our Research Study") */
    .stMarkdown h3 {
        color: #000000 !important;
    }

    /* Do NOT touch custom HTML headers */
    h1, h2 {
        all: unset;
    }

    /* Optional: horizontal rule */
    hr {
        border-color: rgba(0, 0, 0, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True
)


# Page config
st.set_page_config(
    page_title="Bluesky Content Moderation",
    page_icon="🎓",
    layout="wide"
)

# Your Google Apps Script Web App URL
# GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

# Categories for video classification


st.markdown(
    """
    <style>
    .boxed-container {
        border: 1.5px solid rgba(255, 255, 255, 0.25);
        border-radius: 12px;
        padding: 16px;
        background-color: rgba(173, 216, 230, 0.08);
    }
    </style>
    """,
    unsafe_allow_html=True
)
st.markdown(
    """
    <style>
    .stApp {
        background-color: rgba(173, 216, 230, 0.08);
    }
    </style>
    """,
    unsafe_allow_html=True
)

# st.write("Secrets:", st.secrets)
GOOGLE_APPS_SCRIPT_URL = st.secrets["GOOGLE_APPS_SCRIPT_URL"]
PROLIFIC_COMPLETION_CODE = st.secrets["PROLIFIC_COMPLETION_CODE"]



def load_example_posts(query_csv_path, examples_csv_path):
    df_query = pd.read_csv(query_csv_path)
    df_examples = pd.read_csv(examples_csv_path)
    print(f'len query: {len(df_query)}')

    df_merged = df_query.merge(
        df_examples,
        on=["label", "sub_id"],
        how="left",            
        validate="many_to_one" 
    )
    print(f'len merged: {len(df_merged)}')

    return df_merged

def assign_rows_to_user(df, prolific_id, pages_per_user=5):
    total_rows = len(df)
    start_idx = abs(hash(prolific_id)) % total_rows
    
    assigned_indices = [
        (start_idx + i) % total_rows
        for i in range(pages_per_user)
    ]
    
    temp =  df.iloc[assigned_indices].reset_index(drop=True)
    temp = df[df["image"].notna() & (df["image"].astype(str).str.strip() != "")].sample(5)
    return temp


def append_to_public_sheet(data, max_retries=3):
    """Append data to public Google Sheet using Google Apps Script with retry logic"""
    
    for attempt in range(max_retries):
        try:
            # Prepare data with consistent column order - make sure this matches your Google Sheet headers
            payload = {
                'prolific_id': data['prolific_id'],
                'example_id': data['example_id'],
                'answer_yes_no': data['answer_yes_no'],
            }

            
            # Send POST request to Google Apps Script with longer timeout
            response = requests.post(
                GOOGLE_APPS_SCRIPT_URL,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'StreamlitApp/1.0'
                },
                timeout=30,
                verify=True
            )
            
            # Check response
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'success':
                        return True, "Success"
                    else:
                        error_msg = result.get('message', 'Unknown error from Google Apps Script')
                        return False, f"Script error: {error_msg}"
                except json.JSONDecodeError:
                    if "success" in response.text.lower():
                        return True, "Success (HTML response)"
                    else:
                        return False, f"Invalid JSON response: {response.text[:200]}..."
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}..."
                if attempt < max_retries - 1:
                    st.warning(f"Attempt {attempt + 1} failed. Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = f"Request timed out (attempt {attempt + 1}/{max_retries})"
            if attempt < max_retries - 1:
                st.warning(f"Timeout on attempt {attempt + 1}. Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, "Request timed out after multiple attempts"
            
        except requests.exceptions.ConnectionError:
            error_msg = f"Connection error (attempt {attempt + 1}/{max_retries})"
            if attempt < max_retries - 1:
                st.warning(f"Connection failed on attempt {attempt + 1}. Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, "Connection failed after multiple attempts"
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            if attempt < max_retries - 1:
                st.warning(f"Network error on attempt {attempt + 1}. Retrying...")
                time.sleep(2)
                continue
            return False, error_msg
            
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    return False, "Max retries exceeded"


if 'feedback_data' not in st.session_state:
    st.session_state.feedback_data = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if 'current_video_index' not in st.session_state:
    st.session_state.current_video_index = 0
if 'videos' not in st.session_state:
    st.session_state.videos = []
if 'page' not in st.session_state:
    st.session_state.page = 'intro'
if 'prolific_id' not in st.session_state:
    st.session_state.prolific_id = ''
if 'consent_given' not in st.session_state:
    st.session_state.consent_given = False
if 'video_start_time' not in st.session_state:
    st.session_state.video_start_time = None
if 'submission_complete' not in st.session_state:
    st.session_state.submission_complete = False

def intro_page():
    """Introduction and consent page"""
    # Research Study Header with Logo
    st.markdown("""
    <div style="color: #000000; text-align: center; padding: 15px 0;">
        <div style="font-size: 3em; margin-bottom: 8px;">🎓</div>
        <h1 style="color: #1f4e79; margin: 0; font-size: 2.2em;">Bluesky Content Moderation Study</h1>
        <p style="color: #666; margin: 3px 0; font-size: 1em;">Max Planck Institute for Software Systems • Germany</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("""
    ### Welcome to Our Research Study

    Dear participant,

    This survey examines how people judge posts with closely related content and whether content moderation decisions are consistent across similar examples. You will be guided step by step through the survey and asked to make simple judgments.
                
    This study is being conducted by academic researchers from the Max Planck Institute for Software Systems, Germany. Your valuable opinion expressed in this survey may contribute to important research findings. We request you to read the instructions carefully and answer all questions thoughtfully.

    **Privacy & Data Protection:**
    - Results may be published in research forums, but only in aggregate forms (averages, totals)
    - No personal information will be published or shared
    - All information will be protected to the greatest extent allowed by law
    - Data will be kept secured during and after the survey

    **Your Rights:**
    - Participation is completely voluntary
    - You may withdraw at any time without penalty
    - Your responses will remain anonymous
    - You can request data deletion by contacting the researchers
    """)
    
    st.markdown("---")
    st.markdown("**Note:** All fields marked with * are mandatory.")
    
    # Compact layout for ID and consent
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("👤 Participant Information")
        prolific_id = st.text_input("Prolific ID*", 
                                   placeholder="Enter your Prolific ID",
                                   help="Please enter your complete Prolific ID (typically 24 characters)")
        
        # Validate Prolific ID
        prolific_id_valid = False
        if prolific_id:
            if len(prolific_id) < 10:
                st.error("⚠️ Prolific ID seems too short. Please ensure you entered the complete ID.")
            elif len(prolific_id) > 30:
                st.error("⚠️ Prolific ID seems too long. Please check your entry.")
            elif not prolific_id.replace('-', '').replace('_', '').isalnum():
                st.error("⚠️ Prolific ID should contain only letters, numbers, hyphens, and underscores.")
            else:
                prolific_id_valid = True
                st.success("✅ Prolific ID format looks correct.")
    
    with col2:
        st.subheader("📋 Informed Consent")
        
        # Clear consent checkbox with better formatting
        consent = st.checkbox(
            label="**I provide my informed consent to participate***",
            value=False,
            help="Check this box to indicate your agreement to participate"
        )
        
        if consent:
            st.markdown("""
            <div style="background-color: #e8f5e8; padding: 10px; border-radius: 5px; border-left: 4px solid #4CAF50; color: #2e7d32;">
                <strong>✅ Consent Acknowledged</strong><br>
                <span style="color: #2e7d32;">By checking this box, you confirm that you:</span>
                <ul style="margin: 5px 0; color: #2e7d32;">
                    <li>Have read and understood the study information</li>
                    <li>Voluntarily agree to participate in this research</li>
                    <li>Understand your participation is voluntary and anonymous</li>
                    <li>Know you can withdraw at any time</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
    
    # Enable button only when all conditions are met
    can_proceed = prolific_id and prolific_id_valid and consent
    
    st.markdown("---")
    
    if st.button("🚀 Begin Study", disabled=not can_proceed, type="primary", use_container_width=True):
        if can_proceed:
            st.session_state.prolific_id = prolific_id
            st.session_state.consent_given = True
            
            # Load video data
            example_df = load_example_posts("data/posts_to_be_labeled.csv", "data/top_examples_per_subcluster.csv")
            assigned_rows = assign_rows_to_user(
                example_df,
                prolific_id=prolific_id,
                pages_per_user=5
            )

            st.session_state.examples = assigned_rows.to_dict("records")
            st.session_state.page = 'survey'
            st.session_state.current_video_index = 0
            st.session_state.video_start_time = time.time()
            st.rerun()
            
            
        else:
            if not prolific_id:
                st.error("⚠️ Please enter your Prolific ID.")
            elif not prolific_id_valid:
                st.error("⚠️ Please enter a valid Prolific ID.")
            elif not consent:
                st.error("⚠️ Please provide your informed consent to continue.")

def show_drive_image(url, width=450):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        return img
    except Exception as e:
        st.error("Failed to load image")
        st.write(e)

def survey_page():
    """Main survey page with video feedback"""
   
    
    current_idx = st.session_state.current_video_index
    total_videos = len(st.session_state.examples)
    
    # Progress indicator
    st.progress((current_idx + 1) / total_videos)
    st.write(f"Post {current_idx + 1} of {total_videos}")
    
    # Prominent instructions at the top of the page
    st.markdown("""
    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 10px; border-left: 5px solid #2196f3; margin-bottom: 20px;">
        <h3 style="color: #1976d2; margin: 0 0 8px 0; font-size: 1.3em;">📋 Instructions</h3>
        <p style="color: #424242; margin: 0; font-size: 1.1em; font-weight: 500;">
            There are 10 posts shown to you with the same label as mentioned below. Read the examples on the left carefully.
                Then decide if the post which is in the right should be labeled the same. Mark "Yes" or "No". 
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    current_example = st.session_state.examples[current_idx]
    st.markdown(f"""
    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 10px; border-left: 5px solid #2196f3; margin-bottom: 20px;">
        <p style="color: #424242; margin: 0; font-size: 1.1em; font-weight: 500;">
            The label assigned to the left posts is "{current_example['label']}"
        </p>
    </div>
    """, unsafe_allow_html=True)

    
    # Initialize video start time if not set
    if st.session_state.video_start_time is None:
        st.session_state.video_start_time = time.time()
    
    # Create layout: larger video area, smaller summary/feedback area
    col1, col2 = st.columns([1.5, 2])
    
    with col1:
        st.subheader(f"🧾 Example Posts ({current_idx + 1}/5)")

        for i in range(1, 11):
            text = current_example.get(f"text{i}", "")
            img = current_example.get(f"image{i}", "")
            text = str(text)
            if text.strip() == "":
                continue

            st.markdown(f"**Post {i}:**")
            st.write(text)

            if isinstance(img, str) and img.strip() != "":
                c1, c2, c3 = st.columns([1, 2, 1])
                with c2:
                    img = show_drive_image(img)
                    # temp = img.split('?')
                    # img = temp[0] + '?export=download&' + temp[1]
                    st.image(img, width=350)
                    # st.write(img)


            st.markdown("---")
    
    with col2:

        st.subheader("❓ Question")

        st.markdown(f"**{current_example['text']}**")

        if (
            'image' in current_example
            and isinstance(current_example['image'], str)
            and current_example['image'].strip() != ""
        ):
            c1, c2, c3 = st.columns([1, 2, 1])
            with c2:
                img = current_example['image']
                # temp = img.split('?')
                # img = temp[0] + '?export=download&' + temp[1]
                img = show_drive_image(img)
                st.image(img, width=450)
                # st.write(img)
    

        st.markdown("---")

        answer = st.radio(
            "Should this item be labeled the same?",
            options=["Yes", "No"],
            index=None,
            horizontal=True,
            key=f"answer_{current_idx}"
        )
        
       

        # Check if all required fields are filled
        all_fields_filled = (
            answer is not None
        )
        
        # Show validation messages in real-time
        if not all_fields_filled:
            missing_fields = []
            if answer is None:
                missing_fields.append("Yes/No Decision")
            
            
            if missing_fields:
                st.warning(f"⚠️ Please complete: {', '.join(missing_fields)}")
        
        # Determine button text and action based on video position
        is_last_video = current_idx >= total_videos - 1
        
        if is_last_video:
            button_text = "✅ Submit & Complete Study"
            button_help = "Submit your feedback and complete the study"
        else:
            button_text = "➡️ Next Post"
            button_help = f"Continue to post {current_idx + 2} of {total_videos}"
        
        # Action button
        if st.button(
            button_text,
            type="primary" if all_fields_filled else "secondary",
            disabled=not all_fields_filled,
            help=button_help,
            use_container_width=True,
            key=f"submit_btn_{current_idx}"
        ):
            if all_fields_filled:
                # Calculate time spent on this video
                time_spent = time.time() - st.session_state.video_start_time if st.session_state.video_start_time else 0
                
                # Prepare feedback data with consistent ordering
                feedback_data = {
                    'prolific_id': st.session_state.prolific_id,
                    'example_id': current_example['query_cid'],
                    'answer_yes_no': answer
                }
                
                # Add to session state
                st.session_state.feedback_data.append(feedback_data)
                
                # Move to next video or finish
                if is_last_video:
                    # This is the last video, proceed to submit all data
                    submit_all_data()
                else:
                    # Move to next video
                    st.session_state.current_video_index += 1
                    st.session_state.video_start_time = time.time()  # Reset timer for next video
                    st.rerun()

def submit_all_data():
    """Submit all collected data to Google Sheets"""
    if not st.session_state.feedback_data:
        st.error("No data to submit")
        return
    
    success_count = 0
    total_count = len(st.session_state.feedback_data)
    
    # Show submission progress
    st.subheader("📤 Submitting Your Responses...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, feedback in enumerate(st.session_state.feedback_data):
        status_text.text(f"Submitting response {i+1}/{total_count}...")
        progress_bar.progress((i + 1) / total_count)
        
        success, message = append_to_public_sheet(feedback)
        if success:
            success_count += 1
        else:
            st.error(f"Failed to submit response {i+1}: {message}")
        
        time.sleep(0.5)  # Small delay between submissions
    
    # Update submission status
    if success_count == total_count:
        st.session_state.submission_complete = True
        st.success(f"✅ Successfully submitted all {success_count} responses!")
        st.balloons()
    elif success_count > 0:
        st.warning(f"⚠️ Submitted {success_count}/{total_count} responses. Some may have failed.")
        st.session_state.submission_complete = True
    else:
        st.error("❌ Failed to submit responses. Please contact the researchers.")
        st.session_state.submission_complete = False
    
    # Move to summary page
    st.session_state.page = 'summary'
    time.sleep(2)  # Brief pause before redirect
    st.rerun()

def summary_page():
    """Final summary page"""
    st.markdown("""
    <div style="text-align: center; padding: 20px 0;">
        <div style="font-size: 4em; margin-bottom: 10px;">🎉</div>
        <h1 style="color: #1f4e79; margin: 0;">Study Complete!</h1>
        <p style="color: #666; font-size: 1.2em;">Thank you for your participation in the Bluesky Content Moderation Study</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show submission status
    if st.session_state.submission_complete:
        st.success("✅ Your responses have been successfully submitted! Thank you for your responses!")
        
      
    else:
        st.error("❌ There were issues submitting some responses. Please try again!")
    
    

    
    
    
    # # Optional: Reset study button for testing
    # if st.button("🔄 Start New Study Session", help="For testing purposes only"):
    #     # Reset all session state
    #     for key in list(st.session_state.keys()):
    #         del st.session_state[key]
    #     st.rerun()

def main():
    """Main application logic"""
    
    # Route to appropriate page
    if st.session_state.page == 'intro':
        intro_page()
    elif st.session_state.page == 'survey':
        survey_page()
    elif st.session_state.page == 'summary':
        summary_page()
    else:
        intro_page()

if __name__ == "__main__":
    main()
