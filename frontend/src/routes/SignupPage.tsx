import { SignUp } from '@clerk/react'
import AuthLayout from '../components/auth/AuthLayout'

export default function SignupPage() {
  return (
    <AuthLayout
      mode="signup"
      title="Create account"
      subtitle="Get started with spaced-repetition mastery across core CS subjects."
    >
      <div className="clerk-signup-container">
        <SignUp routing="path" path="/signup" signInUrl="/login" />
      </div>
    </AuthLayout>
  )
}
