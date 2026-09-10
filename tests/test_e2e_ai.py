import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cleaner import clean_dataframe
from models import AIProposal, CleaningAction
from validators import validate_cleaning


class TestE2EAI(unittest.TestCase):
    def test_ai_proposal_to_cleaner_flow(self):
        # 1. Mock DataFrame (Actúa como salida del Analyzer)
        df = pd.DataFrame({"Name": [" John ", "Jane "]})
        
        # 2. Mock AI Proposal válida (Simula la respuesta parseada de ai.py)
        ai_proposal = AIProposal(
            action="trim_espacios", column="Name", reason="Espacios detectados", confidence=0.9
        )
        
        # 3. Usuario aprueba la propuesta (Simulación de GUI)
        approved_action = CleaningAction(
            action_id=ai_proposal.action,
            column=ai_proposal.column,
            description=ai_proposal.reason,
            approved=True,  # EL USUARIO APRUEBA
            parameters=ai_proposal.parameters,
            source=ai_proposal.source
        )
        
        # 4. Cleaner ejecuta
        cleaned_df, cleaning_result = clean_dataframe(df, (approved_action,))
        
        # Verificamos que Cleaner hizo el trabajo
        self.assertEqual(cleaned_df["Name"].iloc[0], "John")
        
        # 5. Validator asegura integridad
        val_result = validate_cleaning(df, cleaned_df, (approved_action,), cleaning_result)
        
        # Verificamos que pasó la barrera
        self.assertTrue(val_result.valid)

    def test_ai_invalid_proposal_blocks(self):
        df = pd.DataFrame({"Name": [" John "]})
        
        # Mock de una acción aprobada pero con manipulación de parameters no soportados
        action = CleaningAction(
            action_id="trim_espacios", column="Name", description="Test",
            approved=True, parameters={"malicious": "code"}, source="ai"
        )
        
        # Cleaner ignora los parámetros y registra un warning
        _cleaned_df, cleaning_result = clean_dataframe(df, (action,))
        self.assertTrue(any("Se ignoraron los parámetros" in w for w in cleaning_result.warnings))

if __name__ == '__main__':
    unittest.main()