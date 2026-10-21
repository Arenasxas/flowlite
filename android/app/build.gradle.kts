plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "ar.flowlite"
    compileSdk = 35
    defaultConfig {
        applicationId = "ar.flowlite"
        minSdk = 29 // Android 10: desde ahí se puede grabar el audio de otras apps
        targetSdk = 35
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "2.2." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
    }
    // Firma estable: el keystore vive como secreto del repo (nunca en el código). Sin él, firma de prueba.
    val ks = System.getenv("FLOWLITE_KEYSTORE")
    signingConfigs {
        if (ks != null) create("release") {
            storeFile = file(ks)
            storeType = "pkcs12"
            storePassword = System.getenv("FLOWLITE_KEY_PASS")
            keyAlias = "flowlite"
            keyPassword = System.getenv("FLOWLITE_KEY_PASS")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (ks != null) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }
    // Las mismas indicaciones para la IA que la PC y la app web (prompts.json)
    sourceSets["main"].assets.srcDirs("../../shared")
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    lint { abortOnError = true; warningsAsErrors = false; disable += "ExpiredTargetSdkVersion" }
}

dependencies {
    implementation("androidx.core:core:1.13.1")
    implementation("com.google.android.gms:play-services-auth:21.2.0")
}
