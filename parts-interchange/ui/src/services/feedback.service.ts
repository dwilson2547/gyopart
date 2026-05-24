import { HttpClient } from "@angular/common/http";
import { Injectable } from "@angular/core";
import { environment } from "src/environments/environment";
import { Feedback } from "src/models/Feedback";

@Injectable()
export class FeedbackService {
    constructor(private http: HttpClient) { }

    post_feedback(data: Feedback) {
        return this.http.post(environment.api_url + '/post-feedback/', data)
    }

}