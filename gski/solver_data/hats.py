"""Six Thinking Hats: definitions, forcing questions, sequences."""

HATS = {
    "white": {
        "name": "White Hat",
        "focus": "Facts, data, neutral information",
        "description": "Purely objective. Focus on what information is available, what is missing, and how to get it. No opinions or gut feelings.",
        "questions": [
            "What facts do we have right now?",
            "What information is missing?",
            "What questions do we need to ask to get the data we need?",
            "How can we verify the accuracy of this data?",
            "What are the historical trends related to this issue?",
            "What do the numbers actually say?",
        ],
    },
    "red": {
        "name": "Red Hat",
        "focus": "Emotions, feelings, gut reactions",
        "description": "Express feelings without justification. Emotions are a valid part of decision-making. Keep it fast — under 30 seconds per thought.",
        "questions": [
            "What is your gut reaction to this?",
            "How do you feel about the current situation?",
            "What are your fears or suspicions?",
            "Does this idea excite you or drain you?",
            "What would users/customers feel about this?",
            "What's the emotional tone of this problem?",
        ],
    },
    "black": {
        "name": "Black Hat",
        "focus": "Risks, difficulties, caution",
        "description": "Identify why something might not work. Not about being negative — about being cautious and logical. Find the dangers.",
        "questions": [
            "What are the potential risks or downsides?",
            "Why might this fail?",
            "What are the legal, financial, or technical obstacles?",
            "Does this match our current strategy and constraints?",
            "What is the worst-case scenario?",
            "What have we overlooked?",
        ],
    },
    "yellow": {
        "name": "Yellow Hat",
        "focus": "Benefits, value, optimism",
        "description": "Look for the logical positives. Deliberate effort to find why an idea is valuable and how it could work.",
        "questions": [
            "What are the long-term benefits?",
            "What is the best possible outcome?",
            "How can we make this work?",
            "What value does this add?",
            "What are the opportunities within this challenge?",
            "What strengths can we leverage?",
        ],
    },
    "green": {
        "name": "Green Hat",
        "focus": "Creativity, new ideas, alternatives",
        "description": "Generate new solutions, 'what if' scenarios, out-of-the-box thinking. Criticism is forbidden under this hat.",
        "questions": [
            "Are there any other ways to do this?",
            "What if we had no constraints?",
            "Can we combine two existing ideas into something new?",
            "What are the wild card options?",
            "How would someone from a completely different field solve this?",
            "What's the most unconventional approach possible?",
        ],
    },
    "blue": {
        "name": "Blue Hat",
        "focus": "Process control, organization, summary",
        "description": "The facilitator hat. Define the goal, manage the sequence, summarize findings. Usually at start and end.",
        "questions": [
            "What is our goal for this session?",
            "Which hat should we use next?",
            "What have we achieved so far?",
            "Can someone summarize the main findings?",
            "What are our final action steps?",
            "Are we staying focused on the problem?",
        ],
    },
}

# Recommended sequences by goal (de Bono)
SEQUENCES = {
    "problem_solving": {
        "description": "General problem solving",
        "order": ["blue", "white", "green", "red", "yellow", "black", "blue"],
    },
    "evaluation": {
        "description": "Evaluating an existing idea or proposal",
        "order": ["blue", "red", "white", "yellow", "black", "green", "blue"],
    },
    "quick_decision": {
        "description": "Fast decision making",
        "order": ["blue", "white", "red", "black", "blue"],
    },
    "idea_generation": {
        "description": "Generating new ideas",
        "order": ["blue", "white", "green", "red", "blue"],
    },
    "risk_assessment": {
        "description": "Assessing risks and concerns",
        "order": ["blue", "white", "yellow", "black", "red", "green", "blue"],
    },
}

HAT_ORDER = ["white", "red", "black", "yellow", "green", "blue"]
