# src/discovery_agent.py
"""
Intelligent Discovery Agent for OPNXT
Replaces static forms with dynamic conversation flow
"""

import json
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class DiscoveryContext:
    """Context for discovery conversation"""
    industry: Optional[str] = None
    project_type: str = ''
    conversation_turns: int = 0
    completeness: float = 0.0
    asked_questions: Set[str] = None
    information_gathered: Dict[str, str] = None
    phase_data: Dict[str, List[str]] = None
    
    def __post_init__(self):
        if self.asked_questions is None:
            self.asked_questions = set()
        if self.information_gathered is None:
            self.information_gathered = {}
        if self.phase_data is None:
            self.phase_data = {
                "Planning": [],
                "Requirements": [], 
                "Design": [],
                "Implementation": [],
                "Testing": [],
                "Deployment": [],
                "Maintenance": []
            }

class IntelligentDiscoveryAgent:
    """
    Intelligent agent that replaces OPNXT's static forms with
    dynamic conversation-based requirements gathering
    """
    
    def __init__(self):
        self.context = DiscoveryContext()
        self.question_bank = self._init_question_bank()
        self.industry_detectors = self._init_industry_detectors()
    
    def _init_question_bank(self) -> Dict[str, Dict[str, List[str]]]:
        """Initialize industry and phase-specific questions"""
        return {
            'healthcare': {
                'Planning': [
                    "What type of healthcare facility? (clinic, hospital, specialty practice)",
                    "How many patients do you typically see per day?",
                    "Who are your key stakeholders? (doctors, nurses, admin staff, patients)"
                ],
                'Requirements': [
                    "Do you need HIPAA compliance features?",
                    "What patient data will the system handle?",
                    "Do you need integration with existing EHR systems?"
                ],
                'Design': [
                    "What EHR system do you currently use?", 
                    "Do you need patient portal functionality?",
                    "What are your data backup and security requirements?"
                ]
            },
            'finance': {
                'Planning': [
                    "What type of financial services? (banking, payments, trading)",
                    "Are you B2B or B2C focused?",
                    "What's your typical transaction volume?"
                ],
                'Requirements': [
                    "What regulatory compliance do you need? (PCI DSS, SOX, etc.)",
                    "What fraud prevention features are required?",
                    "Do you need real-time transaction processing?"
                ],
                'Design': [
                    "What payment processors need integration?",
                    "What level of data encryption is required?",
                    "Do you need multi-currency support?"
                ]
            },
            'ecommerce': {
                'Planning': [
                    "What type of products will you sell?",
                    "Expected order volume per day/month?", 
                    "Who is your target customer base?"
                ],
                'Requirements': [
                    "What payment methods do you need to support?",
                    "Do you need inventory management features?",
                    "What shipping and fulfillment capabilities are needed?"
                ],
                'Design': [
                    "Do you need integration with existing inventory systems?",
                    "What third-party services need integration? (Stripe, Shopify, etc.)",
                    "Do you need multi-language or multi-currency support?"
                ]
            },
            'general': {
                'Planning': [
                    "What is the main business problem you're solving?",
                    "Who will be the primary users of this system?",
                    "What's your target timeline for launch?"
                ],
                'Requirements': [
                    "What are the top 3 must-have features?",
                    "Are there any compliance or security requirements?",
                    "What performance requirements do you have?"
                ],
                'Design': [
                    "Do you have preferred technologies or constraints?",
                    "What systems need to integrate with this solution?",
                    "What are your scalability requirements?"
                ]
            }
        }
    
    def _init_industry_detectors(self) -> Dict[str, List[str]]:
        """Keywords to detect industry context"""
        return {
            'healthcare': ['patient', 'medical', 'clinic', 'hospital', 'doctor', 'nurse', 'hipaa', 'ehr'],
            'finance': ['bank', 'payment', 'transaction', 'money', 'account', 'loan', 'pci', 'fraud'],
            'ecommerce': ['store', 'product', 'cart', 'order', 'inventory', 'customer', 'shipping', 'shopify']
        }
    
    def detect_industry(self, user_input: str) -> str:
        """Detect industry from user input"""
        input_lower = user_input.lower()
        
        for industry, keywords in self.industry_detectors.items():
            matches = sum(1 for keyword in keywords if keyword in input_lower)
            if matches >= 2:  # Require at least 2 keyword matches
                return industry
        
        return 'general'
    
    def process_message(self, user_input: str) -> Dict:
        """Process user message and return response with context"""
        self.context.conversation_turns += 1
        
        # First message - detect industry and project type
        if self.context.conversation_turns == 1:
            self.context.industry = self.detect_industry(user_input)
            self.context.project_type = self._extract_project_type(user_input)
        
        # Extract and store information
        self._extract_information(user_input)
        
        # Update completeness
        self._update_completeness()
        
        # Generate response
        if self.context.completeness >= 0.8:
            return self._generate_completion_response()
        else:
            return self._generate_next_questions()
    
    def _extract_project_type(self, user_input: str) -> str:
        """Extract project type from user input"""
        input_lower = user_input.lower()
        
        project_types = {
            'appointment': 'Appointment Management System',
            'scheduling': 'Scheduling System',
            'payment': 'Payment Processing System',
            'inventory': 'Inventory Management System', 
            'store': 'E-commerce Platform',
            'portal': 'User Portal',
            'dashboard': 'Analytics Dashboard',
            'management': 'Management System'
        }
        
        for keyword, project_type in project_types.items():
            if keyword in input_lower:
                return project_type
        
        return 'Custom Business Application'
    
    def _extract_information(self, user_input: str):
        """Extract structured information from user input"""
        input_lower = user_input.lower()
        
        # Extract numbers (patients, volume, etc.)
        import re
        numbers = re.findall(r'\d+', user_input)
        if numbers and any(word in input_lower for word in ['patient', 'user', 'customer', 'transaction']):
            self.context.information_gathered['volume'] = numbers[0]
        
        # Extract compliance mentions
        compliance_keywords = ['hipaa', 'pci', 'gdpr', 'sox', 'compliance']
        for keyword in compliance_keywords:
            if keyword in input_lower:
                self.context.information_gathered[f'{keyword}_compliance'] = True
        
        # Extract technology mentions
        tech_keywords = ['react', 'python', 'java', 'aws', 'azure', 'docker', 'kubernetes']
        for keyword in tech_keywords:
            if keyword in input_lower:
                self.context.information_gathered[f'tech_{keyword}'] = True
        
        # Extract system integrations
        system_keywords = ['epic', 'cerner', 'salesforce', 'shopify', 'stripe', 'paypal']
        for keyword in system_keywords:
            if keyword in input_lower:
                self.context.information_gathered[f'integration_{keyword}'] = True
    
    def _update_completeness(self):
        """Calculate discovery completeness based on gathered information"""
        info_score = min(len(self.context.information_gathered) * 0.15, 0.6)
        questions_score = min(len(self.context.asked_questions) * 0.08, 0.3) 
        turns_score = min(self.context.conversation_turns * 0.05, 0.2)
        
        self.context.completeness = min(info_score + questions_score + turns_score, 1.0)
    
    def _get_next_questions(self) -> List[str]:
        """Get next relevant questions based on context"""
        industry = self.context.industry or 'general'
        current_phase = self._determine_current_phase()
        
        questions_for_phase = self.question_bank.get(industry, {}).get(current_phase, [])
        
        # Return unasked questions
        unasked = [q for q in questions_for_phase if q not in self.context.asked_questions]
        
        if unasked:
            selected = unasked[:2]  # Ask up to 2 questions at once
            self.context.asked_questions.update(selected)
            return selected
        
        return []
    
    def _determine_current_phase(self) -> str:
        """Determine which SDLC phase to focus questions on"""
        phases = ["Planning", "Requirements", "Design", "Implementation", "Testing", "Deployment", "Maintenance"]
        
        # Simple progression based on conversation turns
        if self.context.conversation_turns <= 3:
            return "Planning"
        elif self.context.conversation_turns <= 6:
            return "Requirements"  
        elif self.context.conversation_turns <= 9:
            return "Design"
        else:
            return "Implementation"
    
    def _generate_next_questions(self) -> Dict:
        """Generate response with next questions"""
        next_questions = self._get_next_questions()
        
        if not next_questions:
            # If no more questions, we're probably complete
            self.context.completeness = 0.8
            return self._generate_completion_response()
        
        # Create acknowledgment
        acknowledgment = self._generate_acknowledgment()
        
        # Combine response parts
        response_parts = []
        if acknowledgment:
            response_parts.append(acknowledgment)
        
        response_parts.append("Let me ask about a few more details:")
        response_parts.extend([f"• {q}" for q in next_questions])
        
        return {
            'message': '\n\n'.join(response_parts),
            'context_summary': self._get_context_summary(),
            'ready': False
        }
    
    def _generate_acknowledgment(self) -> str:
        """Generate acknowledgment based on recent information"""
        info = self.context.information_gathered
        
        # Generate acknowledgment based on what was just learned
        if 'volume' in info:
            return f"Great! Understanding your volume of {info['volume']} helps me tailor the solution."
        
        compliance_items = [k for k in info.keys() if 'compliance' in k]
        if compliance_items:
            return f"Perfect! I've noted your {compliance_items[0].replace('_compliance', '').upper()} compliance requirements."
        
        tech_items = [k for k in info.keys() if k.startswith('tech_')]
        if tech_items:
            tech = tech_items[0].replace('tech_', '')
            return f"Excellent! I see you prefer {tech.title()} - I'll keep that in mind for the architecture."
        
        return "I understand." if self.context.conversation_turns % 2 == 0 else "Got it!"
    
    def _generate_completion_response(self) -> Dict:
        """Generate response when discovery is complete"""
        summary = self._generate_project_summary()
        
        return {
            'message': f"Perfect! I have enough information to create your comprehensive project documentation.\n\n{summary}\n\nI'm ready to generate your complete SDLC documentation including Project Charter, Requirements Specification, System Design, and Test Plan.\n\nShall we proceed to generate the documents?",
            'context_summary': self._get_context_summary(),
            'ready': True
        }
    
    def _generate_project_summary(self) -> str:
        """Generate a summary of discovered project information"""
        parts = ["**Project Summary:**"]
        
        if self.context.industry:
            parts.append(f"• Industry: {self.context.industry.title()}")
        
        if self.context.project_type:
            parts.append(f"• Type: {self.context.project_type}")
        
        info = self.context.information_gathered
        if 'volume' in info:
            parts.append(f"• Scale: ~{info['volume']} users/transactions")
        
        compliance = [k.replace('_compliance', '').upper() for k in info.keys() if 'compliance' in k]
        if compliance:
            parts.append(f"• Compliance: {', '.join(compliance)}")
        
        integrations = [k.replace('integration_', '').title() for k in info.keys() if 'integration_' in k]
        if integrations:
            parts.append(f"• Integrations: {', '.join(integrations)}")
        
        parts.append(f"• Information Completeness: {int(self.context.completeness * 100)}%")
        
        return '\n'.join(parts)
    
    def _get_context_summary(self) -> Dict:
        """Get context summary for UI display"""
        return {
            'industry': self.context.industry,
            'project_type': self.context.project_type,
            'completeness': self.context.completeness,
            'turns': self.context.conversation_turns,
            'ready': self.context.completeness >= 0.8,
            'questions_asked': len(self.context.asked_questions),
            'info_gathered': len(self.context.information_gathered)
        }
    
    def export_to_opnxt_format(self) -> Dict[str, List[str]]:
        """Convert discovered information to OPNXT's expected format"""
        # Map discovered information to OPNXT phase structure
        opnxt_answers = {
            "Planning": [],
            "Requirements": [],
            "Design": [],
            "Implementation": [],
            "Testing": [],
            "Deployment": [],
            "Maintenance": []
        }
        
        info = self.context.information_gathered
        
        # Planning phase answers
        if self.context.project_type:
            opnxt_answers["Planning"].append(f"Build {self.context.project_type.lower()}")
        
        if 'volume' in info:
            opnxt_answers["Planning"].append(f"Expected volume: ~{info['volume']} users/transactions")
        
        opnxt_answers["Planning"].append("Timeline: TBD based on scope")
        
        # Requirements phase
        compliance_reqs = [k.replace('_compliance', '').upper() for k in info.keys() if 'compliance' in k]
        if compliance_reqs:
            opnxt_answers["Requirements"].append(f"Compliance required: {', '.join(compliance_reqs)}")
        
        opnxt_answers["Requirements"].append("Core features: TBD based on detailed analysis")
        opnxt_answers["Requirements"].append("Performance: Standard web application performance")
        
        # Design phase
        tech_items = [k.replace('tech_', '').title() for k in info.keys() if k.startswith('tech_')]
        if tech_items:
            opnxt_answers["Design"].append(f"Preferred technologies: {', '.join(tech_items)}")
        
        integrations = [k.replace('integration_', '').title() for k in info.keys() if 'integration_' in k]
        if integrations:
            opnxt_answers["Design"].append(f"Required integrations: {', '.join(integrations)}")
        
        opnxt_answers["Design"].append("Architecture: Modern web application stack")
        
        # Default answers for remaining phases
        opnxt_answers["Implementation"].append("Agile development approach")
        opnxt_answers["Testing"].append("Comprehensive testing strategy with unit, integration, and e2e tests")
        opnxt_answers["Deployment"].append("Cloud deployment with CI/CD pipeline") 
        opnxt_answers["Maintenance"].append("Standard monitoring and maintenance procedures")
        
        return opnxt_answers