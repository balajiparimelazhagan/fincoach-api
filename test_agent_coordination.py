"""
Test script for the multi-agent email processing system.
Tests Intent Classifier and A2A coordination with Transaction Extractor.
"""

import asyncio
import sys
sys.path.insert(0, '/usr/app')

from agent.coordinator import EmailProcessingCoordinator


# Test emails
TEST_EMAILS = [
    {
        "name": "Actual UPI Transaction",
        "subject": "You've spent Rs. 300.00 via UPI",
        "body": """Dear Customer,
        
Rs. 300.00 has been debited from your HDFC Bank Account ending 4319 on 05-Dec-24 to VPA amutha.k@paytm. 
UPI Ref No: 434856234857.
Your available balance is Rs. 12,543.00.

Thank you for banking with us.
HDFC Bank""",
        "expected_intent": "transaction",
        "expected_extracted": True,
    },
    {
        "name": "Promotional Offer",
        "subject": "Promotional offer for PVR movie tickets, starting at ₹92 for GST Bachat Utsav.",
        "body": """Exclusive Offer!

Get flat 50% cashback on movie tickets at PVR. Starting from just Rs. 92!

Limited time offer. Book now using your HDFC Credit Card.

Terms and conditions apply.""",
        "expected_intent": "promotional",
        "expected_extracted": False,
    },
    {
        "name": "Festive Cashback Offer",
        "subject": "Offer: Festive Treats Rs.350 Voucher and up to Rs.240 Cashback on HDFC Bank Credit Card",
        "body": """Celebrate this festive season!

Get Rs. 350 voucher + up to Rs. 240 cashback when you shop with your HDFC Bank Credit Card.

Offer valid till 31st Dec 2024.

Shop now and save big!""",
        "expected_intent": "promotional",
        "expected_extracted": False,
    },
    {
        "name": "Payment Reminder",
        "subject": "Payment Reminder",
        "body": """Dear Customer,

This is a reminder that your credit card payment of Rs. 5,432.00 is due on 15-Dec-2024.

Please pay before the due date to avoid late payment charges.

Pay Now: [Link]

HDFC Bank""",
        "expected_intent": "informational",
        "expected_extracted": False,
    },
    {
        "name": "Account Statement",
        "subject": "Your HDFC Bank - Millennia Credit Card Statement",
        "body": """Dear Customer,

Your credit card statement for the period 01-Nov-24 to 30-Nov-24 is ready.

Total Amount Due: Rs. 12,543.00
Minimum Amount Due: Rs. 543.00
Payment Due Date: 20-Dec-2024

View Statement: [Link]

HDFC Bank""",
        "expected_intent": "informational",
        "expected_extracted": False,
    },
    {
        "name": "Actual Credit Card Transaction",
        "subject": "Alert: Rs 8900.00 spent on HDFC Bank Credit Card",
        "body": """Dear Customer,

Rs. 8900.00 has been charged to your HDFC Bank Credit Card ending 7420 at iPlanet Care Valsaravak on 05-Dec-24.

Available credit limit: Rs. 85,432.00

If you did not make this transaction, please call us immediately.

HDFC Bank""",
        "expected_intent": "transaction",
        "expected_extracted": True,
    },
    {
        "name": "Transaction Reversal/Refund",
        "subject": "Transaction reversal initiated from A GITHUB, INC.",
        "body": """Dear Customer,

A transaction reversal of Rs. 888.40 has been initiated from A GITHUB, INC. to your HDFC Bank Credit Card ending 7420.

This amount will be credited back to your account within 5-7 working days.

Available credit limit: Rs. 86,320.40

Thank you,
HDFC Bank""",
        "expected_intent": "transaction",
        "expected_extracted": True,
        "expected_type": "refund",
    },
]


async def test_email_processing():
    """Test the email processing coordinator"""
    
    print("=" * 80)
    print("MULTI-AGENT EMAIL PROCESSING SYSTEM TEST")
    print("=" * 80)
    print()
    
    # Initialize coordinator
    print("Initializing Email Processing Coordinator...")
    coordinator = EmailProcessingCoordinator()
    print("✓ Coordinator initialized with Intent Classifier and Transaction Extractor\n")
    
    results = {
        "total": len(TEST_EMAILS),
        "correct_intent": 0,
        "correct_extraction": 0,
        "false_positives": 0,  # Promotional classified as transaction
        "false_negatives": 0,  # Transaction classified as promotional
    }
    
    for i, test_email in enumerate(TEST_EMAILS, 1):
        print(f"\n{'='*80}")
        print(f"TEST {i}/{len(TEST_EMAILS)}: {test_email['name']}")
        print(f"{'='*80}")
        print(f"Subject: {test_email['subject']}")
        print(f"Expected Intent: {test_email['expected_intent']}")
        print(f"Expected Extraction: {test_email['expected_extracted']}")
        print()
        
        # Process email
        result = coordinator.process_email(
            message_id=f"test_{i}",
            subject=test_email['subject'],
            body=test_email['body']
        )
        
        # Display results
        print(f"INTENT CLASSIFICATION:")
        print(f"  Intent: {result.intent_classification.intent.value}")
        print(f"  Confidence: {result.intent_classification.confidence:.2f}")
        print(f"  Reasoning: {result.intent_classification.reasoning}")
        print(f"  Should Extract: {result.intent_classification.should_extract}")
        print()
        
        print(f"EXTRACTION RESULT:")
        print(f"  Processed: {result.processed}")
        if result.skip_reason:
            print(f"  Skip Reason: {result.skip_reason}")
        
        if result.transaction:
            print(f"  Transaction Found:")
            print(f"    Amount: {result.transaction.amount}")
            print(f"    Type: {result.transaction.transaction_type}")
            print(f"    Category: {result.transaction.category}")
            print(f"    Description: {result.transaction.description}")
            if result.transaction.transactor:
                print(f"    Transactor: {result.transaction.transactor}")
        else:
            print(f"  Transaction: None")
        
        # Validate results
        print()
        print("VALIDATION:")
        intent_correct = result.intent_classification.intent.value == test_email['expected_intent']
        extraction_correct = result.processed == test_email['expected_extracted']
        
        # Check transaction type if specified
        type_correct = True
        if 'expected_type' in test_email and result.transaction:
            expected_type = test_email['expected_type']
            actual_type = result.transaction.transaction_type.value if hasattr(result.transaction.transaction_type, 'value') else str(result.transaction.transaction_type)
            type_correct = actual_type == expected_type
            if not type_correct:
                print(f"  ✗ Transaction type WRONG (got {actual_type}, expected {expected_type})")
            else:
                print(f"  ✓ Transaction type CORRECT ({actual_type})")
        
        if intent_correct:
            print("  ✓ Intent classification CORRECT")
            results["correct_intent"] += 1
        else:
            print(f"  ✗ Intent classification WRONG (got {result.intent_classification.intent.value}, expected {test_email['expected_intent']})")
            
            # Check for false positives/negatives
            if test_email['expected_intent'] == 'transaction' and result.intent_classification.intent.value == 'promotional':
                results["false_negatives"] += 1
            elif test_email['expected_intent'] == 'promotional' and result.intent_classification.intent.value == 'transaction':
                results["false_positives"] += 1
        
        if extraction_correct:
            print("  ✓ Extraction decision CORRECT")
            results["correct_extraction"] += 1
        else:
            print(f"  ✗ Extraction decision WRONG (processed={result.processed}, expected={test_email['expected_extracted']})")
    
    # Summary
    print("\n")
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total Tests: {results['total']}")
    print(f"Correct Intent Classifications: {results['correct_intent']}/{results['total']} ({results['correct_intent']/results['total']*100:.1f}%)")
    print(f"Correct Extraction Decisions: {results['correct_extraction']}/{results['total']} ({results['correct_extraction']/results['total']*100:.1f}%)")
    print(f"False Positives (Promo → Transaction): {results['false_positives']}")
    print(f"False Negatives (Transaction → Promo): {results['false_negatives']}")
    print()
    
    if results['correct_intent'] == results['total'] and results['correct_extraction'] == results['total']:
        print("✓ ALL TESTS PASSED!")
    else:
        print("✗ Some tests failed. Review the results above.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_email_processing())
