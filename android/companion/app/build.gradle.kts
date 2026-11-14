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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
dependencies {
    implementation("androidx.webkit:webkit:1.14.0")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test:core:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
}
