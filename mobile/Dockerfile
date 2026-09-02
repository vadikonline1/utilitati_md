FROM node:20-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH=$PATH:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/opt/android-sdk/emulator

RUN apt-get update && apt-get install -y \
    openjdk-17-jdk \
    wget \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p ${ANDROID_HOME}/cmdline-tools

RUN wget -q https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip \
    -O /tmp/cmdline-tools.zip \
    && unzip -q /tmp/cmdline-tools.zip -d ${ANDROID_HOME}/cmdline-tools \
    && mv ${ANDROID_HOME}/cmdline-tools/cmdline-tools ${ANDROID_HOME}/cmdline-tools/latest \
    && rm /tmp/cmdline-tools.zip

RUN yes | sdkmanager --licenses

RUN sdkmanager \
    "platform-tools" \
    "platforms;android-35" \
    "build-tools;35.0.0"

WORKDIR /app

COPY package*.json ./

# Use --unsafe-perm so postinstall scripts run reliably as root in the container.
RUN npm install --unsafe-perm

COPY . .

# Generate the native Android project (android/ folder) inside the image.
RUN npx expo prebuild --platform android

# The generated Gradle wrapper lives in /app/android; the project root is /app.
# Default action: build a release APK (signed with the default Expo/debug keystore).
# Usable directly, or override with your own gradle command:
#   docker run --rm -v "$(pwd)/dist:/output" utilitati-mobile \
#     sh -c 'cd android && ./gradlew assembleRelease && cp app/build/outputs/apk/release/app-release.apk /output/utilitati-md-release.apk'
CMD ["sh", "-c", "cd android && ./gradlew assembleRelease"]