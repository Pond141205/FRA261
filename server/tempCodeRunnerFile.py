from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, create_engine
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timezone
import os, json,pytz, numpy as np