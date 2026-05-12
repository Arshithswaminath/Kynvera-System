import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.injaaz.app',
  appName: 'Amaan',
  webDir: 'static',
  server: {
    // For development - uncomment and set your Render URL to test against live server
    // url: 'https://your-app.onrender.com',
    // cleartext: true
    
    // For production - leave commented to use bundled web assets
  },
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      launchAutoHide: true,
      backgroundColor: "#d21725",
      androidSplashResourceName: "splash",
      androidScaleType: "CENTER_CROP",
      showSpinner: true,
      androidSpinnerStyle: "large",
      iosSpinnerStyle: "small",
      spinnerColor: "#ffffff",
      splashFullScreen: true,
      splashImmersive: true
    },
    StatusBar: {
      style: "dark",
      backgroundColor: "#d21725"
    },
    Camera: {
      permissions: {
        camera: "Allow Amaan to access your camera to take photos for inspections.",
        photos: "Allow Amaan to access your photos to attach to reports."
      }
    }
  },
  android: {
    allowMixedContent: true,
    buildOptions: {
      keystorePath: undefined,
      keystorePassword: undefined,
      keystoreAlias: undefined,
      keystoreAliasPassword: undefined
    }
  },
  ios: {
    scheme: "Amaan"
  }
};

export default config;

