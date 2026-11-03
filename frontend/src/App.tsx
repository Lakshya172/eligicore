import { useEffect } from "react";
import { Layout } from "./components/Layout";
import { EmptyState } from "./components/ui";
import { About } from "./pages/About";
import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";
import { Opportunities } from "./pages/Opportunities";
import { OpportunityDetail } from "./pages/OpportunityDetail";
import { Profile } from "./pages/Profile";
import { Link, useRoute, type Route } from "./router";
import { ProfileProvider } from "./state/ProfileContext";

const TITLES: Record<Route["name"], string> = {
  landing: "EligiCore — understand your eligibility before you apply",
  dashboard: "Dashboard · EligiCore",
  opportunities: "Opportunities · EligiCore",
  opportunity: "Opportunity · EligiCore",
  profile: "Profile · EligiCore",
  about: "How it works · EligiCore",
  "not-found": "Page not found · EligiCore",
};

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case "landing":
      return <Landing />;
    case "dashboard":
      return <Dashboard />;
    case "opportunities":
      return <Opportunities />;
    case "opportunity":
      return <OpportunityDetail jobId={route.jobId} />;
    case "profile":
      return <Profile />;
    case "about":
      return <About />;
    case "not-found":
      return (
        <div className="page">
          <EmptyState
            title="Page not found"
            action={
              <Link to="" className="button button--secondary">
                Go to the home page
              </Link>
            }
          />
        </div>
      );
  }
}

export function App() {
  const route = useRoute();
  useEffect(() => {
    document.title = TITLES[route.name];
  }, [route.name]);
  return (
    <ProfileProvider>
      <Layout route={route}>
        <Page key={route.name === "opportunity" ? `opportunity-${route.jobId}` : route.name} route={route} />
      </Layout>
    </ProfileProvider>
  );
}
