import { SignIn } from "@clerk/react";
import AuthLayout from "../components/auth/AuthLayout";

const clerkAppearance = {
  variables: {
    colorPrimary: "#39d4c7",
    colorBackground: "rgba(7, 16, 32, 0.0)",
    colorInputBackground: "rgba(10, 22, 38, 0.75)",
    colorInputText: "#d8e2ea",
    colorText: "#d8e2ea",
    colorTextSecondary: "#9fb0bf",
    colorNeutral: "#9fb0bf",
    colorDanger: "#ff7f8b",
    borderRadius: "0.75rem",
    fontFamily: "'Satoshi', 'Segoe UI', sans-serif",
  },
  elements: {
    card: { background: "transparent", boxShadow: "none", padding: 0 },
    rootBox: { width: "100%" },
    formButtonPrimary: {
      background: "#39d4c7",
      color: "#05131a",
      fontWeight: 600,
      borderRadius: "999px",
    },
    formFieldInput: {
      background: "rgba(10, 22, 38, 0.75)",
      border: "1px solid rgba(126, 157, 181, 0.34)",
      color: "#d8e2ea",
      borderRadius: "0.5rem",
    },
    footerAction: { color: "#9fb0bf" },
    footerActionLink: { color: "#39d4c7" },
    identityPreviewText: { color: "#d8e2ea" },
    socialButtonsBlockButton: {
      border: "1px solid rgba(126, 157, 181, 0.28)",
      background: "rgba(16, 28, 42, 0.7)",
      color: "#d8e2ea",
      borderRadius: "0.75rem",
    },
    dividerLine: { background: "rgba(126, 157, 181, 0.2)" },
    dividerText: { color: "#9fb0bf" },
  },
}

export default function LoginPage() {
  return (
    <AuthLayout
      mode="login"
      title="Welcome back"
      subtitle="Sign in securely with email, Google, or GitHub."
    >
      <div className="clerk-signin-container">
        <SignIn
          routing="path"
          path="/login"
          signUpUrl="/signup"
          fallbackRedirectUrl="/dashboard"
          appearance={clerkAppearance}
        />
      </div>
    </AuthLayout>
  );
}
