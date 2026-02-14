import { Amplify } from 'aws-amplify';

// Values sourced from .env — see .env.example for how to populate after CDK deployment.
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_USER_POOL_CLIENT_ID,
    },
  },
});
