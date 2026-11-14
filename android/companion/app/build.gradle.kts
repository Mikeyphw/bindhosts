plugins {
    id("com.android.application")
}
android {
    namespace = "com.mikeyphw.bindhosts"
    compileSdk = 36
    defaultConfig {
        applicationId = "com.mikeyphw.bindhosts"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0-foundation"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies {
    implementation("androidx.webkit:webkit:1.14.0")
}
