"""
Category Auto-Mapper Service
Provides standard category definitions and validation for the FinCoach application
"""
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.category import Category


class CategoryMapper:
    """
    Manages standard category definitions and validation
    """
    
    # Category mapping rules with keywords and patterns
    CATEGORY_RULES = {
        'Housing': [
            'rent', 'mortgage', 'property tax', 'housing society', 'maintenance',
            'apartment', 'flat', 'hoa', 'association', 'society maintenance'
        ],
        
        'Utilities': [
            'electricity', 'power', 'bescom', 'mseb', 'water bill', 'sewage',
            'municipal', 'gas', 'lpg', 'cylinder', 'internet', 'broadband',
            'wifi', 'airtel', 'jio', 'bsnl', 'tata sky', 'dish tv'
        ],
        
        'Food': [
            'swiggy', 'zomato', 'uber eats', 'restaurant', 'cafe', 'coffee',
            'mcdonald', 'kfc', 'domino', 'pizza', 'food', 'grocery',
            'supermarket', 'bigbasket', 'amazon fresh', 'dmart', 'reliance fresh',
            'more', 'star bazaar', 'spencer'
        ],
        
        'Transport': [
            'uber', 'ola', 'rapido', 'petrol', 'diesel', 'fuel', 'hp', 'bharat petroleum',
            'indian oil', 'shell', 'metro', 'bus', 'train', 'irctc', 'fastag',
            'parking', 'toll', 'taxi'
        ],
        
        'Shopping': [
            'amazon', 'flipkart', 'myntra', 'ajio', 'nykaa', 'shopping',
            'retail', 'store', 'mall', 'shopper', 'lifestyle', 'pantaloons',
            'westside', 'max fashion', 'h&m', 'zara', 'decathlon'
        ],
        
        'Subscriptions': [
            'netflix', 'prime', 'hotstar', 'spotify', 'youtube premium',
            'apple music', 'subscription', 'membership', 'annual fee',
            'renewal', 'recurring'
        ],
        
        'Health': [
            'hospital', 'clinic', 'doctor', 'pharmacy', 'medicine', 'apollo',
            'fortis', 'max healthcare', 'manipal', 'medplus', 'netmeds',
            '1mg', 'pharmeasy', 'gym', 'fitness', 'yoga', 'cult fit'
        ],
        
        'Entertainment': [
            'movie', 'cinema', 'pvr', 'inox', 'game', 'gaming', 'steam',
            'playstation', 'xbox', 'sports', 'event', 'concert', 'show',
            'theatre', 'bookmyshow', 'paytm insider'
        ],
        
        'Travel': [
            'flight', 'airline', 'indigo', 'spicejet', 'air india', 'vistara',
            'makemytrip', 'goibibo', 'cleartrip', 'hotel', 'oyo', 'treebo',
            'airbnb', 'booking.com', 'travel', 'vacation', 'trip'
        ],
        
        'Personal Care': [
            'salon', 'spa', 'beauty', 'grooming', 'parlor', 'barber',
            'lakme', 'vlcc', 'natural', 'wellness'
        ],
        
        'Education': [
            'school', 'college', 'university', 'tuition', 'course', 'udemy',
            'coursera', 'byju', 'unacademy', 'books', 'stationery',
            'exam fee', 'education'
        ],
        
        'Family & Relationships': [
            'gift', 'birthday', 'anniversary', 'wedding', 'ferns n petals',
            'archies', 'hallmark', 'flower', 'celebration'
        ],
        
        'Income': [
            'salary', 'refund', 'cashback', 'credit', 'payment received',
            'interest credited', 'dividend', 'bonus', 'incentive'
        ],
        
        'Investments': [
            'mutual fund', 'sip', 'stock', 'zerodha', 'groww', 'upstox',
            'etmoney', 'paytm money', 'invest', 'equity', 'shares',
            'gold', 'digital gold'
        ],
        
        'Loans & EMIs': [
            'emi', 'loan', 'credit card', 'hdfc loan', 'icici loan',
            'sbi loan', 'home loan', 'car loan', 'personal loan',
            'bajaj finserv', 'repayment'
        ],
        
        'Savings & Transfers': [
            'transfer', 'upi', 'neft', 'imps', 'rtgs', 'savings',
            'deposit', 'fd', 'fixed deposit', 'recurring deposit'
        ],
        
        'Fees & Charges': [
            'bank charges', 'annual fee', 'late fee', 'penalty',
            'service charge', 'processing fee', 'gst', 'convenience fee'
        ],
        
        'Taxes': [
            'income tax', 'tds', 'advance tax', 'property tax',
            'professional tax', 'gst payment'
        ],
        
        'Donations': [
            'donation', 'charity', 'ngo', 'temple', 'church', 'mosque',
            'gurudwara', 'relief fund', 'pm cares', 'give india'
        ],
    }
    
    @classmethod
    def get_all_categories(cls) -> list[str]:
        """
        Get list of all standard category names
        
        Returns:
            List of all category names including Miscellaneous
        """
        return list(cls.CATEGORY_RULES.keys()) + ['Miscellaneous']
    
    @classmethod
    def validate_category(cls, category: str) -> str:
        """
        Validate if a category is in the standard list
        
        Args:
            category: Category name to validate
            
        Returns:
            The category if valid, otherwise 'Miscellaneous'
        """
        all_categories = cls.get_all_categories()
        
        # Direct match
        if category in all_categories:
            return category
        
        # Case-insensitive match
        category_lower = category.lower()
        for cat in all_categories:
            if cat.lower() == category_lower:
                return cat
        
        # Return Miscellaneous if not found
        return 'Miscellaneous'


# Singleton instance
category_mapper = CategoryMapper()
