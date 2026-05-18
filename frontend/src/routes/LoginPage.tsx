import { SignIn } from '@clerk/react'
import AuthLayout from '../components/auth/AuthLayout'

export default function LoginPage() {
  return (
    <AuthLayout
      mode="login"
      title="Welcome back"
      subtitle="Sign in securely with email, Google, or GitHub."
    >
      <div className="clerk-signin-container">
        <SignIn routing="path" path="/login" signUpUrl="/signup" />
      </div>
    </AuthLayout>
  )
}
