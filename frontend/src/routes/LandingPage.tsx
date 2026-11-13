import { useAuth } from '../auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { Link } from 'react-router-dom'
import './landing.css'

export function LandingReadingView({ authenticated = false }: { authenticated?: boolean }) {
  return <div className="landing reading-sheet">
    <section className="study-intro">
      <div className="study-intro__copy">
        <p className="study-label">Operating systems / Databases / Networks</p>
        <h1>Close the book.<br /><em>Keep the idea.</em></h1>
        <p className="study-intro__description">A quiet place to practise computer science. Explain a concept in your own words, check your reasoning, and return to the questions that need another look.</p>
        <div className="study-intro__actions"><Link className="study-action" to={authenticated ? '/dashboard' : '/signup'}>{authenticated ? 'Open your study desk' : 'Create your study space'} <span aria-hidden="true">↗</span></Link><Link to={authenticated ? '/review/setup' : '/login'}>{authenticated ? 'Configure a review' : 'Already studying here? Sign in'}</Link></div>
        <p className="study-intro__note">Your answer first. Reference and model feedback after.</p>
      </div>
      <article className="study-example" aria-label="Illustrative study card">
        <header><span className="study-label">Example card · not a recorded session</span><span className="study-example__folio">01</span></header>
        <p className="study-label">Operating systems / Memory</p>
        <h2>What does paging solve, and what does it leave behind?</h2>
        <p className="study-example__prompt">Explain internal and external fragmentation before opening the reference.</p>
        <details><summary>Open the reference answer <span aria-hidden="true">＋</span></summary><p>Paging maps fixed-size virtual pages to physical frames. Non-contiguous frames avoid external fragmentation, while unused space within an allocated frame can still cause internal fragmentation.</p></details>
        <footer>Read the question. Try to recall. Then check.</footer>
      </article>
    </section>
    <section className="study-method" aria-label="Study method">
      <div><span className="study-label">01 / Scope</span><h2>Choose one thread.</h2><p>Select topics for a focused session, or use a learning path to order the work.</p></div>
      <div><span className="study-label">02 / Recall</span><h2>Make your reasoning visible.</h2><p>Write an explanation before seeing the reference. Skipping and not knowing remain distinct actions.</p></div>
      <div><span className="study-label">03 / Revisit</span><h2>Use the feedback.</h2><p>Inspect model feedback and available source context, then follow the recorded review schedule.</p></div>
    </section>
  </div>
}

export default function LandingPage() {
  usePageTitle('')
  const { status } = useAuth()
  return <LandingReadingView authenticated={status === 'authenticated'} />
}
