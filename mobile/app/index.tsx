import { Redirect } from "expo-router";

import { LoadingState, Screen } from "../src/components/Ui";
import { useSession } from "../src/providers/SessionProvider";

export default function Index() {
  const { ready, authenticated } = useSession();

  if (!ready) {
    return (
      <Screen>
        <LoadingState label="Preparando Diaglob..." />
      </Screen>
    );
  }

  return (
    <Redirect
      href={authenticated ? "/(tabs)" : "/login"}
    />
  );
}
