import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from app.api.main import app
from app.db.database import get_db
from app.db.models import User, RegistrationState, OTPCode
import datetime

# Mock the database session
mock_session = AsyncMock()

async def override_get_db():
    yield mock_session

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


class TestAuthAPI(unittest.TestCase):
    
    def setUp(self):
        mock_session.reset_mock()
        # By default scalars().first() returns None
        mock_session.execute.return_value.scalars.return_value.first.return_value = None

    def test_register_step1_success(self):
        response = client.post("/auth/register/step1", json={"email": "test@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Proceed to step 2", response.json()["message"])
        mock_session.add.assert_called()
        mock_session.commit.assert_called()

    def test_register_step1_email_already_exists(self):
        # Mock user exists
        mock_user = User(email="test@example.com")
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_user
        
        response = client.post("/auth/register/step1", json={"email": "test@example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Email already registered")

    def test_register_step2_passwords_mismatch(self):
        response = client.post("/auth/register/step2", json={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "different_password"
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Passwords do not match")

    @patch("app.api.auth.generate_otp", return_value="123456")
    def test_register_step2_success(self, mock_generate_otp):
        # Setup registration state step 1 completed
        mock_reg_state = RegistrationState(email="test@example.com", step=1)
        
        # When querying RegistrationState, return the mock
        async def side_effect(*args, **kwargs):
            mock_result = MagicMock()
            mock_result.scalars.return_value.first.return_value = mock_reg_state
            return mock_result
            
        mock_session.execute.side_effect = side_effect

        response = client.post("/auth/register/step2", json={
            "email": "test@example.com",
            "password": "password123",
            "confirm_password": "password123"
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("OTP sent", response.json()["message"])
        self.assertEqual(mock_reg_state.step, 2)

    def test_register_verify_otp_invalid(self):
        response = client.post("/auth/register/verify-otp", json={
            "email": "test@example.com",
            "otp": "000000"
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid or expired OTP")

    def test_forgot_password_success(self):
        mock_user = User(email="test@example.com")
        mock_session.execute.return_value.scalars.return_value.first.return_value = mock_user
        
        response = client.post("/auth/forgot-password", json={"email": "test@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("OTP has been sent", response.json()["message"])
        mock_session.add.assert_called()

    def test_reset_password_mismatch(self):
        response = client.post("/auth/reset-password", json={
            "email": "test@example.com",
            "otp": "123456",
            "new_password": "new_password123",
            "confirm_password": "different_password"
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Passwords do not match")

if __name__ == "__main__":
    unittest.main()
