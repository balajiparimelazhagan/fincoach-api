"""
Amount Analysis Agent for analyzing transaction amounts and detecting outliers.
Uses Google ADK to intelligently reason about outliers before excluding them.
Part of the Spending Analysis agentic system.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
from decimal import Decimal
import statistics
import json
import logging

from google.adk.agents.llm_agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class AmountAnalysisResult:
    """Result of amount analysis"""
    avg_amount: Decimal
    min_amount: Decimal
    max_amount: Decimal
    variance_percent: float
    is_fixed_amount: bool  # <5% variance = fixed
    is_variable_amount: bool  # 5-50% variance
    is_highly_variable: bool  # >50% variance
    outliers_detected: List[Decimal]  # Detected and excluded outliers
    outlier_reasons: Dict[str, str]  # Reason for excluding each outlier
    used_amounts: List[Decimal]  # Amounts used for calculation (after outlier removal)
    reasoning: str = ""
    
    def to_dict(self):
        return {
            "avg_amount": float(self.avg_amount),
            "min_amount": float(self.min_amount),
            "max_amount": float(self.max_amount),
            "variance_percent": self.variance_percent,
            "is_fixed_amount": self.is_fixed_amount,
            "is_variable_amount": self.is_variable_amount,
            "is_highly_variable": self.is_highly_variable,
            "outliers_detected": [float(o) for o in self.outliers_detected],
            "outlier_reasons": self.outlier_reasons,
            "used_amounts_count": len(self.used_amounts),
            "reasoning": self.reasoning,
        }


class AmountAnalysisAgent:
    """
    Agent for analyzing transaction amounts and detecting outliers.
    
    Responsibilities:
    1. Calculate amount statistics
    2. Use LLM to intelligently detect outliers
    3. Exclude outliers with reasoning
    4. Calculate variance metrics
    5. Classify amount pattern (fixed, variable, highly variable)
    """
    
    def __init__(self):
        """Initialize the amount analysis agent"""
        self.agent = Agent(
            model="gemini-2.5-flash",
            name="amount_analysis_agent",
            description="Analyzes transaction amounts and intelligently detects outliers",
            instruction=self._get_system_instruction(),
        )
        logger.info("Amount Analysis Agent initialized")
    
    def _get_system_instruction(self) -> str:
        """Get system instruction for amount analysis"""
        return """You are an expert at analyzing transaction amounts and detecting outliers.

Your task is to:
1. Analyze a list of transaction amounts
2. Identify outliers (amounts that seem unusual or one-time)
3. Provide reasoning for why an amount is an outlier
4. Calculate statistics on the remaining amounts

Outlier Detection Rules:
- Use statistical methods (IQR, Z-score) as baseline
- But also use DOMAIN KNOWLEDGE and CONTEXT:
  
Examples of outliers to EXCLUDE:
- A tenant payment of ₹16,170 when others are ₹1,660 (probably one-time advance or adjustment)
- A grocery purchase of ₹5,000 when others are ₹400-₹600 (probably bulk/festival purchase)
- An electricity bill of ₹3,500 when others are ₹800-₹1,200 (might be meter replacement)
  
Examples of amounts to KEEP (variable but normal):
- Electricity bills ranging ₹800-₹1,200 (seasonal variation is normal)
- Grocery purchases varying by amount (normal shopping variation)
- Phone recharges all ₹199 but one is ₹349 (new plan, not outlier)

Your Response Format:
Return ONLY a valid JSON object with:
{
    "outliers": [{"amount": 16170, "reason": "One-time tenant advance, >10x normal amount"}],
    "reasoning": "Detected 1 outlier from 5 transactions. Remaining 4 show consistent ₹1,600-₹1,800 pattern.",
    "should_exclude": true
}

Be conservative: If unsure, KEEP the amount (don't exclude unless clearly anomalous)."""

    def analyze_amounts(
        self,
        amounts: List[Decimal],
        transactor_name: str = "",
        bucket_info: Optional[dict] = None,
    ) -> AmountAnalysisResult:
        """
        Analyze transaction amounts for patterns and outliers.
        
        Args:
            amounts: List of transaction amounts
            transactor_name: Name of transactor (for context)
            bucket_info: Optional bucket distribution info for context
        
        Returns:
            AmountAnalysisResult with analysis and outlier detection
        """
        if not amounts:
            logger.warning("No amounts to analyze")
            return AmountAnalysisResult(
                avg_amount=Decimal("0"),
                min_amount=Decimal("0"),
                max_amount=Decimal("0"),
                variance_percent=0.0,
                is_fixed_amount=False,
                is_variable_amount=False,
                is_highly_variable=False,
                outliers_detected=[],
                outlier_reasons={},
                used_amounts=[],
                reasoning="No amounts to analyze",
            )
        
        logger.info(f"Analyzing {len(amounts)} amounts for {transactor_name}")
        
        # Use LLM to detect outliers
        outliers_result = self._detect_outliers_with_llm(amounts, transactor_name)
        outliers = outliers_result.get("outliers", [])
        outlier_reasons = {str(o["amount"]): o["reason"] for o in outliers}
        
        # Create set of outlier amounts for filtering
        outlier_amounts = {Decimal(str(o["amount"])) for o in outliers}
        
        # Filter out outliers
        used_amounts = [a for a in amounts if a not in outlier_amounts]
        
        if not used_amounts:
            # All were outliers, use original
            logger.warning(f"All amounts were detected as outliers, using original")
            used_amounts = amounts
            outliers = []
            outlier_reasons = {}
        
        logger.info(f"Using {len(used_amounts)} amounts after removing {len(outliers)} outliers")
        
        # Calculate statistics on filtered amounts
        avg = sum(used_amounts) / len(used_amounts)
        min_amt = min(used_amounts)
        max_amt = max(used_amounts)
        
        # Calculate variance
        variance_percent = self._calculate_variance_percent(used_amounts, avg)
        
        # Classify amount pattern
        is_fixed = variance_percent < 5
        is_variable = 5 <= variance_percent <= 50
        is_highly_variable = variance_percent > 50
        
        result = AmountAnalysisResult(
            avg_amount=avg,
            min_amount=min_amt,
            max_amount=max_amt,
            variance_percent=variance_percent,
            is_fixed_amount=is_fixed,
            is_variable_amount=is_variable,
            is_highly_variable=is_highly_variable,
            outliers_detected=[Decimal(str(o["amount"])) for o in outliers],
            outlier_reasons=outlier_reasons,
            used_amounts=used_amounts,
            reasoning=outliers_result.get("reasoning", ""),
        )
        
        logger.info(
            f"Amount analysis: avg={avg}, variance={variance_percent:.1f}%, "
            f"fixed={is_fixed}, variable={is_variable}, highly_variable={is_highly_variable}"
        )
        
        return result
    
    def _detect_outliers_with_llm(self, amounts: List[Decimal], transactor_name: str) -> dict:
        """Use LLM to detect outliers with reasoning"""
        try:
            from google.genai import Client
            client = Client()
            
            # Prepare context
            amounts_str = ", ".join([f"₹{a}" for a in amounts])
            context = f"""Transaction Amounts to Analyze:
{amounts_str}

Transactor: {transactor_name}
Count: {len(amounts)} transactions
Min: ₹{min(amounts)}
Max: ₹{max(amounts)}
Mean: ₹{sum(amounts)/len(amounts):.2f}
"""
            
            prompt = f"""{self._get_system_instruction()}

{context}

Analyze the amounts above and identify outliers."""
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            
            response_text = response.text.strip()
            
            # Try to parse JSON
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            result = json.loads(response_text.strip())
            logger.info(f"LLM detected {len(result.get('outliers', []))} outliers")
            
            return result
            
        except Exception as e:
            logger.warning(f"LLM outlier detection failed: {e}, using statistical fallback")
            return self._detect_outliers_statistical(amounts)
    
    def _detect_outliers_statistical(self, amounts: List[Decimal]) -> dict:
        """Statistical fallback for outlier detection using IQR method"""
        if len(amounts) < 4:
            return {"outliers": [], "reasoning": "Too few amounts for statistical outlier detection"}
        
        sorted_amounts = sorted(amounts)
        n = len(sorted_amounts)
        
        # Calculate Q1, Q3
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        q1 = sorted_amounts[q1_idx]
        q3 = sorted_amounts[q3_idx]
        iqr = q3 - q1
        
        # IQR method: outliers are outside [Q1 - 1.5*IQR, Q3 + 1.5*IQR]
        factor = Decimal('1.5')
        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr
        
        outliers = []
        for amt in amounts:
            if amt < lower_bound or amt > upper_bound:
                outliers.append({
                    "amount": float(amt),
                    "reason": f"Outside IQR bounds [{float(lower_bound):.2f}, {float(upper_bound):.2f}]"
                })
        
        reasoning = f"Statistical IQR method: {len(outliers)} outliers detected from {len(amounts)} amounts"
        
        return {
            "outliers": outliers,
            "reasoning": reasoning,
            "should_exclude": len(outliers) > 0,
        }
    
    def _calculate_variance_percent(self, amounts: List[Decimal], mean: Decimal) -> float:
        """Calculate coefficient of variation"""
        if not amounts or mean == 0:
            return 0.0
        
        # Standard deviation
        squared_diffs = [(a - mean) ** 2 for a in amounts]
        variance = sum(squared_diffs) / len(amounts)
        std_dev = variance ** Decimal('0.5')
        
        # Coefficient of variation as percentage
        cv = (std_dev / mean) * 100
        
        return float(cv)
