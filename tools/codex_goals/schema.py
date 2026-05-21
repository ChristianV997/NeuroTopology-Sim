
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class GoalPreset: goal_id:str; name:str; mode:str; contribution_target:str; required_surfaces:List[str]; required_outputs:List[str]; required_make_targets:List[str]; validation_commands:List[str]; guardrails:List[str]; forbidden_patterns:List[str]; success_criteria:List[str]; pr_body_sections:List[str]
@dataclass
class GoalSurface: name:str; description:str
@dataclass
class GoalGuardrail: name:str; blocked:bool=True
@dataclass
class GoalValidationCommand: command:str
@dataclass
class ContributionScorecard: dimensions:Dict[str,int]; minimum_total:int
@dataclass
class RenderedPrompt: mission:str; sections:List[str]
@dataclass
class PRBodyTemplate: sections:List[str]
@dataclass
class GoalValidationResult: ok:bool; violations:List[str]
