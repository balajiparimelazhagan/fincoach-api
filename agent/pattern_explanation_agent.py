"""
Pattern Explanation Agent

LLM-based agent that ONLY judges and explains deterministic pattern outputs.
NEVER computes intervals, dates, or patterns directly.

Responsibilities:
1. Generate human-readable explanations
2. Validate borderline deterministic patterns
3. Assign friendly pattern names
4. Provide confidence reasoning
"""
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime
from google.adk.agents.llm_agent import Agent

from agent.pattern_discovery_engine import PatternCase, AmountBehaviorType, PatternCandidate


class PatternExplanationAgent:
    """
    LLM agent for pattern explanation and naming.
    
    CRITICAL CONSTRAINTS:
    - Takes deterministic pattern output as input
    - NEVER computes intervals, dates, or patterns
    - ONLY generates explanations and names
    - All logic is in the prompt, not in code
    """
    
    def __init__(self):
        self.agent = Agent(
            model='gemini-2.5-flash',
            name='pattern_explanation_agent',
            description='Explains and validates recurring financial patterns discovered by deterministic algorithms.',
            instruction=self._build_instruction()
        )
    
    def _build_instruction(self) -> str:
        """Build the LLM instruction that constrains behavior"""
        return """
You are a financial pattern explanation specialist.

YOUR ROLE:
- Generate human-readable explanations for recurring financial patterns
- Suggest friendly display names for patterns
- Explain confidence scores in user-friendly terms
- Validate whether borderline patterns make sense

CRITICAL CONSTRAINTS - YOU MUST NEVER:
- Compute or suggest time intervals
- Calculate dates or next payment dates
- Detect patterns from raw transactions
- Change pattern types or classifications
- Modify confidence scores

INPUT FORMAT:
You will receive deterministic pattern analysis results containing:
- Transactor name
- Pattern case (FIXED_MONTHLY, VARIABLE_MONTHLY, etc.)
- Interval in days
- Amount behavior (FIXED, VARIABLE, HIGHLY_VARIABLE)
- Average amount and range
- Confidence score
- Number of observations

OUTPUT FORMAT:
You must return a JSON object with:
{
    "display_name": "Friendly name for this pattern (e.g., 'Netflix Subscription', 'Monthly Rent')",
    "explanation_text": "Clear explanation of the pattern behavior for end users",
    "confidence_reasoning": "Why this confidence score makes sense",
    "is_valid": true/false (should this pattern be shown to users?)
}

EXPLANATION GUIDELINES:
- Use simple, non-technical language
- Focus on what the user needs to know
- Highlight timing reliability and amount predictability
- Mention any concerns (high variability, low confidence)
- Be concise (2-3 sentences)

DISPLAY NAME GUIDELINES:
- Use the transactor name as base
- Add context if pattern type helps (e.g., "Monthly", "Quarterly")
- Keep it short and recognizable
- Examples: "Spotify Premium", "Electricity Bill (Monthly)", "Mutual Fund SIP"

VALIDATION RULES:
- Mark as invalid if:
  - Confidence < 0.3 (too unreliable)
  - Only 3 observations and high variability
  - Pattern doesn't make logical sense for this transactor
- Otherwise mark as valid

Remember: You are explaining patterns that were already discovered deterministically.
Your job is to make them understandable and trustworthy for users.
"""
    
    def explain_pattern(
        self,
        transactor_name: str,
        pattern_case: PatternCase,
        interval_days: Optional[int],
        amount_behavior: AmountBehaviorType,
        avg_amount: Decimal,
        min_amount: Decimal,
        max_amount: Decimal,
        confidence: float,
        observation_count: int,
        currency_symbol: str = "₹"
    ) -> Dict:
        """
        Generate explanation for a discovered pattern.
        
        Args:
            transactor_name: Name of the transactor (e.g., "Netflix", "PNB Housing")
            pattern_case: Deterministic pattern case
            interval_days: Interval in days (None for flexible)
            amount_behavior: Amount consistency classification
            avg_amount: Average transaction amount
            min_amount: Minimum amount observed
            max_amount: Maximum amount observed
            confidence: Confidence score (0.0 to 1.0)
            observation_count: Number of transactions in pattern
            currency_symbol: Currency symbol for display
        
        Returns:
            Dict with display_name, explanation_text, confidence_reasoning, is_valid
        """
        # Build context for LLM
        pattern_context = self._build_pattern_context(
            transactor_name=transactor_name,
            pattern_case=pattern_case,
            interval_days=interval_days,
            amount_behavior=amount_behavior,
            avg_amount=avg_amount,
            min_amount=min_amount,
            max_amount=max_amount,
            confidence=confidence,
            observation_count=observation_count,
            currency_symbol=currency_symbol
        )
        
        # Query LLM
        prompt = f"""
Analyze this recurring pattern and provide explanation:

{pattern_context}

Return your response as a JSON object with the required fields.
"""
        
        try:
            response = self.agent.prompt(prompt)
            
            # Parse LLM response (expecting JSON)
            import json
            result = json.loads(response)
            
            # Validate response structure
            if not all(k in result for k in ['display_name', 'explanation_text', 'confidence_reasoning', 'is_valid']):
                raise ValueError("LLM response missing required fields")
            
            return result
            
        except Exception as e:
            # Fallback to deterministic explanation if LLM fails
            return self._fallback_explanation(
                transactor_name=transactor_name,
                pattern_case=pattern_case,
                amount_behavior=amount_behavior,
                confidence=confidence
            )
    
    def _build_pattern_context(
        self,
        transactor_name: str,
        pattern_case: PatternCase,
        interval_days: Optional[int],
        amount_behavior: AmountBehaviorType,
        avg_amount: Decimal,
        min_amount: Decimal,
        max_amount: Decimal,
        confidence: float,
        observation_count: int,
        currency_symbol: str
    ) -> str:
        """Build context string for LLM"""
        context = f"""
Transactor: {transactor_name}
Pattern Type: {pattern_case.value}
Interval: {interval_days} days ({self._interval_to_human(interval_days, pattern_case)})
Amount Behavior: {amount_behavior.value}
Average Amount: {currency_symbol}{avg_amount:.2f}
Amount Range: {currency_symbol}{min_amount:.2f} to {currency_symbol}{max_amount:.2f}
Confidence Score: {confidence:.2f} ({int(confidence * 100)}%)
Observations: {observation_count} transactions
"""
        return context.strip()
    
    def _interval_to_human(self, interval_days: Optional[int], pattern_case: PatternCase) -> str:
        """Convert interval to human-readable string"""
        if interval_days is None:
            return "varies within month"
        
        if pattern_case == PatternCase.FIXED_MONTHLY or pattern_case == PatternCase.VARIABLE_MONTHLY:
            return "approximately monthly"
        elif pattern_case == PatternCase.BI_MONTHLY:
            return "every 2 months"
        elif pattern_case == PatternCase.QUARTERLY:
            return "quarterly"
        elif interval_days == 7:
            return "weekly"
        elif interval_days == 14:
            return "bi-weekly"
        else:
            return f"every {interval_days} days"
    
    def _fallback_explanation(
        self,
        transactor_name: str,
        pattern_case: PatternCase,
        amount_behavior: AmountBehaviorType,
        confidence: float
    ) -> Dict:
        """
        Fallback explanation when LLM fails.
        Deterministic, safe, generic.
        """
        # Generate basic display name
        if pattern_case == PatternCase.FIXED_MONTHLY:
            display_name = f"{transactor_name} (Monthly)"
        elif pattern_case == PatternCase.BI_MONTHLY:
            display_name = f"{transactor_name} (Bi-Monthly)"
        elif pattern_case == PatternCase.QUARTERLY:
            display_name = f"{transactor_name} (Quarterly)"
        else:
            display_name = transactor_name
        
        # Generate basic explanation
        if amount_behavior == AmountBehaviorType.FIXED:
            amount_desc = "consistent amount"
        elif amount_behavior == AmountBehaviorType.VARIABLE:
            amount_desc = "varying amount"
        else:
            amount_desc = "highly variable amount"
        
        explanation = f"Recurring payment to {transactor_name} with {amount_desc}."
        
        # Confidence reasoning
        if confidence >= 0.8:
            conf_reason = "High confidence due to consistent pattern."
        elif confidence >= 0.5:
            conf_reason = "Moderate confidence based on observed behavior."
        else:
            conf_reason = "Lower confidence due to variability or limited data."
        
        return {
            "display_name": display_name,
            "explanation_text": explanation,
            "confidence_reasoning": conf_reason,
            "is_valid": confidence >= 0.3  # Validation threshold
        }
    
    def validate_borderline_pattern(
        self,
        pattern_case: PatternCase,
        confidence: float,
        observation_count: int,
        amount_cv: float
    ) -> bool:
        """
        Validate borderline patterns using deterministic rules + LLM judgment.
        
        Returns:
            True if pattern should be kept, False if rejected
        """
        # Hard deterministic rules first
        if confidence < 0.25:
            return False  # Too low, always reject
        
        if observation_count < 3:
            return False  # Not enough data
        
        if amount_cv > 0.8:
            return False  # Too variable
        
        # For borderline cases (0.25 <= confidence < 0.4), ask LLM
        if 0.25 <= confidence < 0.4:
            prompt = f"""
Should this pattern be shown to users?

Pattern Type: {pattern_case.value}
Confidence: {confidence:.2f}
Observations: {observation_count}
Amount Variability: {amount_cv:.2f}

Answer with just "YES" or "NO" and brief reasoning.
"""
            try:
                response = self.agent.prompt(prompt).strip().upper()
                return response.startswith("YES")
            except:
                # If LLM fails, use conservative threshold
                return confidence >= 0.35
        
        # High enough confidence, keep it
        return True
    
    def batch_explain_patterns(
        self,
        patterns: List[Dict]
    ) -> List[Dict]:
        """
        Batch process multiple patterns for efficiency.
        
        Args:
            patterns: List of pattern dicts with all required fields
        
        Returns:
            List of explanation dicts
        """
        results = []
        for pattern in patterns:
            explanation = self.explain_pattern(
                transactor_name=pattern['transactor_name'],
                pattern_case=PatternCase(pattern['pattern_case']),
                interval_days=pattern.get('interval_days'),
                amount_behavior=AmountBehaviorType(pattern['amount_behavior']),
                avg_amount=Decimal(str(pattern['avg_amount'])),
                min_amount=Decimal(str(pattern['min_amount'])),
                max_amount=Decimal(str(pattern['max_amount'])),
                confidence=pattern['confidence'],
                observation_count=pattern['observation_count'],
                currency_symbol=pattern.get('currency_symbol', '₹')
            )
            results.append(explanation)
        
        return results
