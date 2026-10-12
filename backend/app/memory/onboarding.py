class ColdStartOnboarding:
    """
    Solves the Cold Start problem for users with < 5 sessions.
    Injects prompt logic to explicitly solicit goals and preferences,
    bypassing the initial density requirement for HDBSCAN clustering.
    """
    
    ONBOARDING_PROMPT = """
    [SYSTEM ONBOARDING MODE]: You are interacting with a new user. Since you do not yet have historical context,
    you must actively and politely ask lightweight clarifying questions to gather their core goals, technical preferences, 
    or interests. Incorporate these questions naturally into your response to their query.
    """
    
    def __init__(self, session_threshold: int = 5):
        self.threshold = session_threshold
        
    def needs_onboarding(self, session_count: int) -> bool:
        return session_count < self.threshold
        
    def inject_prompt(self, user_prompt: str, session_count: int) -> str:
        """
        If the user is in cold-start mode, prepends the onboarding directive.
        """
        if self.needs_onboarding(session_count):
            return f"{self.ONBOARDING_PROMPT}\n\nUser: {user_prompt}"
        return user_prompt
