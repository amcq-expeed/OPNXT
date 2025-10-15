import { createContext, useContext } from "react";
import type { User } from "./api";

export interface UserContextValue {
  user: User | null;
  persona: string | null;
}

const defaultValue: UserContextValue = {
  user: null,
  persona: null,
};

export const UserContext = createContext<UserContextValue>(defaultValue);

export function useUserContext(): UserContextValue {
  return useContext(UserContext);
}
