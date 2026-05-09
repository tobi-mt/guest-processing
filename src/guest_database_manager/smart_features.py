"""Enhanced app module with AI-powered smart features for guest management."""

import logging
from typing import Optional

import streamlit as st

from guest_database_manager.database import GuestDatabase
from guest_database_manager.ai_assistant import AIAssistant, FollowUpManager

logger = logging.getLogger(__name__)


def display_smart_features(db: GuestDatabase, ai_assistant: Optional[AIAssistant]) -> None:
    """Display AI-powered smart features tab."""
    st.header("✨ Smart Features")
    
    if not ai_assistant:
        st.warning("⚠️ AI features are not available. Please set the OPENAI_API_KEY environment variable to enable smart features.")
        st.info("💡 **To enable AI features:**\n\n"
                "1. Get an OpenAI API key from https://platform.openai.com/api-keys\n"
                "2. Set the environment variable: `export OPENAI_API_KEY='your-key-here'`\n"
                "3. Restart the application")
        return
    
    # Create sub-tabs for different smart features
    smart_tab1, smart_tab2, smart_tab3, smart_tab4 = st.tabs([
        "🎯 Guest Scoring", 
        "🔍 Smart Research", 
        "📧 Follow-ups", 
        "❓ Interview Questions"
    ])
    
    with smart_tab1:
        display_guest_scoring(db, ai_assistant)
    
    with smart_tab2:
        display_smart_research(db, ai_assistant)
    
    with smart_tab3:
        display_follow_ups(db, ai_assistant)
    
    with smart_tab4:
        display_interview_questions(db, ai_assistant)


def display_guest_scoring(db: GuestDatabase, ai_assistant: AIAssistant) -> None:
    """Display AI-powered guest scoring and recommendations."""
    st.subheader("🎯 Intelligent Guest Scoring & Recommendations")
    st.write("Get AI-powered insights on which guests are the best fit for your podcast.")
    
    # Get unprocessed guests
    guests_list = db.get_all_guests()
    unprocessed = [g for g in guests_list if not g.get('is_processed')]
    
    if not unprocessed:
        st.info("📝 No unprocessed guests to score. All caught up!")
        return
    
    st.write(f"**{len(unprocessed)} unprocessed guests** ready for scoring")
    
    if st.button("🎯 Score All Unprocessed Guests", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        scored_guests = []
        
        for idx, guest in enumerate(unprocessed):
            status_text.text(f"Analyzing guest {idx + 1} of {len(unprocessed)}: {guest.get('full_name', 'Unknown')}...")
            
            try:
                # Get AI insights
                insights = ai_assistant.research_guest_from_text(guest)
                
                # Get scoring from guest_recommender if available
                try:
                    from guest_database_manager.guest_recommender import score_guest
                    score_result = score_guest(guest)
                    fit_score = score_result.get("total_score", 0)
                    category = score_result.get("category", "Unknown")
                except Exception as e:
                    logger.warning(f"Could not use guest_recommender: {e}")
                    fit_score = insights.get("fit_score", 5)
                    category = "AI Scored"
                
                scored_guests.append({
                    "name": guest.get("full_name", "Unknown"),
                    "email": guest.get("email", ""),
                    "fit_score": fit_score,
                    "category": category,
                    "themes": insights.get("themes", []),
                    "concerns": insights.get("concerns", "None"),
                    "guest_id": guest["id"]
                })
                
            except Exception as e:
                logger.error(f"Error scoring guest {guest.get('full_name')}: {e}")
            
            progress_bar.progress((idx + 1) / len(unprocessed))
        
        status_text.text("✅ Scoring complete!")
        
        # Sort by fit score
        scored_guests.sort(key=lambda x: x["fit_score"], reverse=True)
        
        # Display results
        st.subheader("📊 Scoring Results")
        
        for guest in scored_guests[:10]:  # Show top 10
            with st.expander(f"⭐ {guest['name']} - Score: {guest['fit_score']}/10 ({guest['category']})"):
                st.write(f"**Email:** {guest['email']}")
                st.write(f"**Category:** {guest['category']}")
                if guest.get('themes'):
                    st.write("**Key Themes:**")
                    if isinstance(guest['themes'], list):
                        for theme in guest['themes']:
                            st.write(f"- {theme}")
                    else:
                        st.write(guest['themes'])
                if guest.get('concerns'):
                    st.write(f"**Potential Concerns:** {guest['concerns']}")
                
                # Quick actions
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("✅ Accept", key=f"quick_accept_{guest['guest_id']}"):
                        st.session_state[f"show_accept_dialog_{guest['guest_id']}"] = True
                        st.rerun()
                with col2:
                    if st.button("❌ Reject", key=f"quick_reject_{guest['guest_id']}"):
                        st.session_state[f"show_reject_dialog_{guest['guest_id']}"] = True
                        st.rerun()


def display_smart_research(db: GuestDatabase, ai_assistant: AIAssistant) -> None:
    """Display smart guest research features."""
    st.subheader("🔍 Smart Guest Research")
    st.write("Automatically analyze guest applications and gather insights.")
    
    guests_list = db.get_all_guests()
    
    # Select a guest to research
    guest_names = [f"{g.get('full_name', 'Unknown')} ({g.get('email', 'no email')})" for g in guests_list]
    
    if not guest_names:
        st.info("📝 No guests available. Import some guest data first!")
        return
    
    selected_idx = st.selectbox("Select a guest to research:", range(len(guest_names)), 
                                format_func=lambda x: guest_names[x])
    
    selected_guest = guests_list[selected_idx]
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.write(f"**Name:** {selected_guest.get('full_name', 'Unknown')}")
        st.write(f"**Email:** {selected_guest.get('email', 'N/A')}")
        st.write(f"**Profession:** {selected_guest.get('profession', 'N/A')}")
        if selected_guest.get('website'):
            st.write(f"**Website:** {selected_guest.get('website')}")
    
    with col2:
        if st.button("🔍 Analyze Guest", type="primary"):
            with st.spinner("Analyzing guest profile..."):
                insights = ai_assistant.research_guest_from_text(selected_guest)
                st.session_state[f"research_{selected_guest['id']}"]=  insights
                st.success("✅ Analysis complete!")
    
    # Display research results if available
    if st.session_state.get(f"research_{selected_guest['id']}"):
        insights = st.session_state[f"research_{selected_guest['id']}"]
        
        st.subheader("📋 AI Analysis Results")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if "fit_score" in insights:
                st.metric("Fit Score", f"{insights['fit_score']}/10")
            
            if "themes" in insights:
                st.write("**Key Themes:**")
                if isinstance(insights['themes'], list):
                    for theme in insights['themes']:
                        st.write(f"- {theme}")
                else:
                    st.write(insights['themes'])
        
        with col2:
            if "conversation_angles" in insights:
                st.write("**Conversation Angles:**")
                if isinstance(insights['conversation_angles'], list):
                    for angle in insights['conversation_angles']:
                        st.write(f"- {angle}")
                else:
                    st.write(insights['conversation_angles'])
        
        if "concerns" in insights:
            st.write("**Potential Concerns:**")
            st.write(insights['concerns'])
        
        if "best_timing" in insights:
            st.write("**Best Timing:**")
            st.write(insights['best_timing'])


def display_follow_ups(db: GuestDatabase, ai_assistant: AIAssistant) -> None:
    """Display follow-up management features."""
    st.subheader("📧 Smart Follow-Up Management")
    st.write("Automatically identify guests who need follow-up and generate reminder emails.")
    
    # Create follow-up manager
    follow_up_mgr = FollowUpManager(str(db.db_path))
    
    # Get guests needing follow-up
    days_threshold = st.slider("Days since last contact:", 3, 30, 7)
    
    if st.button("🔍 Find Guests Needing Follow-Up"):
        with st.spinner("Searching for guests..."):
            guests_needing_followup = follow_up_mgr.get_guests_needing_follow_up(days_threshold)
            st.session_state['followup_guests'] = guests_needing_followup
    
    if st.session_state.get('followup_guests'):
        guests = st.session_state['followup_guests']
        
        if not guests:
            st.success(f"✅ No guests need follow-up! All contacts are recent (within {days_threshold} days).")
        else:
            st.write(f"**Found {len(guests)} guests** who haven't been contacted in {days_threshold}+ days:")
            
            for guest in guests:
                with st.expander(f"📧 {guest['full_name']} - Last contact: {guest.get('email_sent_at', 'Unknown')}"):
                    st.write(f"**Email:** {guest.get('email', 'N/A')}")
                    st.write(f"**Status:** {guest.get('email_status', 'Unknown')}")
                    
                    # Generate follow-up email
                    if st.button("✨ Generate Follow-Up Email", key=f"followup_{guest['id']}"):
                        with st.spinner("Generating follow-up email..."):
                            days_since = days_threshold  # Simplified
                            context = "Previously accepted for Mirror Talk podcast, awaiting next steps"
                            
                            followup_email = ai_assistant.generate_follow_up_email(
                                guest, context, days_since
                            )
                            
                            if followup_email:
                                st.text_area(
                                    "Follow-Up Email Draft",
                                    value=followup_email,
                                    height=150,
                                    key=f"followup_draft_{guest['id']}"
                                )


def display_interview_questions(db: GuestDatabase, ai_assistant: AIAssistant) -> None:
    """Display AI-generated interview questions."""
    st.subheader("❓ Smart Interview Question Generator")
    st.write("Generate thoughtful, personalized interview questions based on guest information.")
    
    guests_list = db.get_all_guests()
    
    if not guests_list:
        st.info("📝 No guests available. Import some guest data first!")
        return
    
    # Select a guest
    guest_names = [f"{g.get('full_name', 'Unknown')} ({g.get('profession', 'Unknown')})" for g in guests_list]
    selected_idx = st.selectbox("Select a guest:", range(len(guest_names)), 
                                format_func=lambda x: guest_names[x])
    
    selected_guest = guests_list[selected_idx]
    
    # Display guest info
    st.write(f"**Name:** {selected_guest.get('full_name', 'Unknown')}")
    st.write(f"**Profession:** {selected_guest.get('profession', 'N/A')}")
    if selected_guest.get('passionate_topics'):
        st.write(f"**Passionate About:** {selected_guest.get('passionate_topics')}")
    
    num_questions = st.slider("Number of questions to generate:", 5, 20, 10)
    
    if st.button("✨ Generate Interview Questions", type="primary"):
        with st.spinner("Generating personalized questions..."):
            questions = ai_assistant.generate_interview_questions(selected_guest, num_questions)
            st.session_state[f"questions_{selected_guest['id']}"] = questions
            st.success(f"✅ Generated {len(questions)} questions!")
    
    # Display questions if available
    if st.session_state.get(f"questions_{selected_guest['id']}"):
        questions = st.session_state[f"questions_{selected_guest['id']}"]
        
        st.subheader("💬 Generated Interview Questions")
        
        for idx, question in enumerate(questions, 1):
            st.write(f"**{idx}.** {question}")
        
        # Export option
        if st.button("📥 Copy All Questions"):
            questions_text = "\n\n".join([f"{idx}. {q}" for idx, q in enumerate(questions, 1)])
            st.code(questions_text, language="text")
            st.info("💡 Copy the text above and paste it into your notes!")
