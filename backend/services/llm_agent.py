"""
LLM Agent Service
Handles all LLM interactions using Groq (primary) or OpenAI (fallback)
Manages persona-based responses and interview flow
"""

from typing import List, Dict, Any, Optional
from groq import Groq
from openai import OpenAI
from utils.config import settings
from utils.role_data import get_role_context, get_scoring_rubric
import json


class LLMAgent:
    """
    Manages LLM interactions for interview simulation
    Supports multiple personas and role-specific behavior
    """

    def __init__(self, persona: str = "Efficient"):
        self.persona = persona

        # Use Groq with llama-3.3-70b-versatile
        if not settings.GROQ_API_KEY or not settings.GROQ_API_KEY.strip():
            raise ValueError("GROQ_API_KEY is required")

        self.client = Groq(api_key=settings.GROQ_API_KEY)
        self.model = "llama-3.3-70b-versatile"
        self.provider = "groq"
        print(f"✓ Using Groq LLM with {self.model}")

        self.persona_instructions = self._get_persona_instructions()

    def _get_persona_instructions(self) -> str:
        """Get system instructions based on persona"""
        persona_guides = {
            "Confused": "The user may be uncertain or need guidance. Be patient, provide clear explanations, and gently redirect if needed.",
            "Efficient": "The user prefers concise, direct communication. Keep responses brief and to the point. Don't over-explain.",
            "Chatty": "The user tends to go off-topic. Be friendly but firm in redirecting to interview questions. Keep the conversation professional.",
            "Edge-case": "The user may provide unusual or unexpected responses. Handle these gracefully, set boundaries, and guide back to relevant answers.",
            "Adaptive": """ADAPTIVE MODE: Automatically detect and adapt to the user's communication style:
            - If user is confused/uncertain: Be patient, provide clear explanations, and gently guide them
            - If user is efficient/direct: Keep responses brief and concise, don't over-explain
            - If user is chatty/goes off-topic: Be friendly but firm in redirecting to interview questions
            - If user provides edge-case/unusual responses: Handle gracefully, set boundaries, and guide back
            
            Continuously analyze the user's responses and adjust your communication style accordingly. 
            Be flexible and responsive to their needs while maintaining professional interview standards.""",
        }
        return persona_guides.get(self.persona, persona_guides["Adaptive"])

    def generate_greeting(self, role: str, user_name: str) -> str:
        """Generate interview greeting based on role"""
        adaptive_note = (
            "I'll adapt to your communication style throughout our conversation."
            if self.persona == "Adaptive"
            else ""
        )

        system_prompt = f"""You are a professional interview agent conducting a mock {role} interview.
        
{self.persona_instructions}

Generate a warm, professional greeting that:
1. Welcomes the candidate
2. Explains the interview structure (5-7 questions)
3. Mentions anti-cheating monitoring
4. Sets expectations for honest, detailed answers
{f'5. Mention that you will adapt to their communication style' if self.persona == 'Adaptive' else ''}

Keep it concise (3-4 sentences)."""

        user_prompt = f"Generate a greeting for {user_name} for a {role} interview."

        response = self._call_llm(system_prompt, user_prompt)
        return response

    def evaluate_and_decide(
        self,
        user_answer: str,
        current_question: str,
        conversation_history: List[Dict[str, str]],
        cheating_summary: Dict[str, Any],
        role: str,
    ) -> Dict[str, Any]:
        """
        Evaluate user's answer and decide next action
        Returns: {
            "response": str,
            "followup": bool,
            "followup_question": str (optional),
            "complete": bool
        }
        """
        role_context = get_role_context(role)
        rubric = get_scoring_rubric(role)

        system_prompt = f"""You are a professional interview agent conducting a {role} interview.

{self.persona_instructions}

Role Context: {role_context}

Scoring Rubric: {rubric}

Current Question: {current_question}

Evaluate the candidate's answer and decide:
1. Provide brief acknowledgment/feedback on their answer (1-2 sentences)
2. Decide if a follow-up question is needed (only if answer was vague or needs clarification)
3. If no follow-up, just acknowledge and indicate readiness for next question

Respond with JSON:
{{
    "response": "your acknowledgment",
    "followup": true/false,
    "followup_question": "optional follow-up question",
    "complete": false
}}"""

        context = f"""Conversation so far: {len(conversation_history)} messages
        
User's latest answer: {user_answer}

Cheating events detected: {cheating_summary.get('total_events', 0)}"""

        response = self._call_llm(system_prompt, context, json_mode=True)

        try:
            decision = json.loads(response)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            decision = {
                "response": "Thank you for your answer.",
                "followup": False,
                "complete": False,
            }

        return decision

    def generate_final_feedback(
        self,
        conversation_history: List[Dict[str, str]],
        role: str,
        cheating_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate comprehensive final feedback
        Returns structured feedback with scores and recommendations
        """
        rubric = get_scoring_rubric(role)

        system_prompt = f"""You are a professional interview evaluator for {role} positions.

Analyze the complete interview conversation and provide detailed feedback.

Scoring Rubric: {rubric}

{self.persona_instructions}

Generate feedback in JSON format:
{{
    "technical_score": 1-10,
    "communication_score": 1-10,
    "confidence_score": 1-10,
    "overall_summary": "2-3 sentence summary",
    "strengths": ["strength 1", "strength 2", "strength 3"],
    "weaknesses": ["weakness 1", "weakness 2"],
    "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
}}

Base scores on:
- Technical accuracy and depth
- Communication clarity
- Confidence and professionalism
- Ability to articulate thoughts"""

        # Prepare conversation context
        conversation_text = "\n".join(
            [f"{msg['role']}: {msg['content']}" for msg in conversation_history]
        )

        # Check if candidate actually answered questions
        user_messages = [msg for msg in conversation_history if msg["role"] == "user"]
        total_user_words = sum(len(msg["content"].split()) for msg in user_messages)

        user_prompt = f"""Interview Transcript:
{conversation_text}

Cheating Summary:
{json.dumps(cheating_summary, indent=2)}

User provided {len(user_messages)} answers with {total_user_words} total words.

CRITICAL: If the candidate provided no meaningful answers or ended interview immediately without participating (0 messages or <10 words), 
give 0/10 for ALL score categories and provide feedback explaining lack of participation. Do not give 1/10 - give 0/10.
For minimal participation, scores should reflect the quality (0-2 range for very poor performance).

Provide comprehensive feedback."""

        response = self._call_llm(system_prompt, user_prompt, json_mode=True)

        try:
            # Try to parse JSON response
            feedback = json.loads(response)

            # Validate required fields
            required_fields = [
                "technical_score",
                "communication_score",
                "confidence_score",
                "overall_summary",
                "strengths",
                "weaknesses",
                "recommendations",
            ]
            for field in required_fields:
                if field not in feedback:
                    raise ValueError(f"Missing required field: {field}")

            # Add cheating summary to feedback
            feedback["cheating_summary"] = cheating_summary
            print("✓ Successfully generated feedback")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠ Feedback parsing error: {e}")
            print(f"Raw response: {response[:200]}...")

            # Check if interview was actually completed
            user_messages = [
                msg for msg in conversation_history if msg["role"] == "user"
            ]
            total_words = sum(len(msg["content"].split()) for msg in user_messages)

            # Fallback feedback
            if len(user_messages) == 0 or total_words < 10:
                feedback = {
                    "technical_score": 0,
                    "communication_score": 0,
                    "confidence_score": 0,
                    "overall_summary": "Interview was ended without providing any meaningful responses. No evaluation possible.",
                    "strengths": [],
                    "weaknesses": [
                        "Did not participate in the interview",
                        "Ended session immediately without providing any answers",
                    ],
                    "recommendations": [
                        "Complete the full interview",
                        "Provide thoughtful answers to questions",
                        "Engage with the interviewer",
                    ],
                    "cheating_summary": cheating_summary,
                }
            else:
                feedback = {
                    "technical_score": 5,
                    "communication_score": 5,
                    "confidence_score": 5,
                    "overall_summary": "Thank you for completing the interview. Due to a technical issue, we couldn't generate detailed feedback.",
                    "strengths": [
                        "Completed the interview session",
                        "Engaged with questions",
                    ],
                    "weaknesses": ["Technical feedback generation issue"],
                    "recommendations": [
                        "Practice more interviews",
                        "Review role-specific topics",
                        "Work on communication clarity",
                    ],
                    "cheating_summary": cheating_summary,
                }

        return feedback

    def _call_llm(
        self, system_prompt: str, user_prompt: str, json_mode: bool = False
    ) -> str:
        """Call Groq LLM"""
        try:
            # Add JSON instruction if json_mode (Groq doesn't have response_format)
            system_content = system_prompt
            if json_mode:
                system_content += (
                    "\n\nIMPORTANT: Respond with valid JSON only. No additional text."
                )

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=2048,
            )

            content = response.choices[0].message.content
            if not content:
                raise ValueError("Empty response from Groq")
            return content

        except Exception as e:
            print(f"❌ LLM Error: {str(e)}")
            print(f"Error type: {type(e).__name__}")

            # Return minimal valid JSON if json_mode expected
            if json_mode:
                return '{"response": "I apologize, but I\'m experiencing technical difficulties.", "followup": false, "complete": false}'
            return "I apologize, but I'm experiencing technical difficulties. Please try again."
