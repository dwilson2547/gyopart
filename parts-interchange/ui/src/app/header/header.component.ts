import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { AbstractControl, FormBuilder, FormControl, FormGroup, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialog, MatDialogRef } from '@angular/material/dialog';
import { Feedback } from 'src/models/Feedback';
import { FeedbackService } from 'src/services/feedback.service';
import { LocalStorage } from '../constants/localstorage';
import { LocalStoreCar } from 'src/interfaces/LocalStoreCars';
import { Select2Option } from 'ng-select2-component';

@Component({
  selector: 'app-header',
  templateUrl: './header.component.html',
  styleUrls: ['./header.component.scss']
})
export class HeaderComponent implements OnInit {
  savedCars: Select2Option[] = [];
  constructor(public dialog: MatDialog) { }
  openFeedbackDialog() {
    this.dialog.open(FeedbackDialog, {
      width: '70%'
    })
  }
  ngOnInit(): void {
    this.populate_quick_access();
  }

  populate_quick_access() {
    let val = localStorage.getItem(LocalStorage.ClientCars);
    if (val) {
      let parsed_val: LocalStoreCar[] = JSON.parse(val);
      parsed_val.forEach(element => {
        let lbl = `${element.year} ${element.make} ${element.model} ${element.trim} ${element.engine}`
        this.savedCars.push({ value: element.id, label: lbl })
      });
    }
  }
}
@Component({
  selector: 'feedback-panel',
  templateUrl: 'feedback-panel.html',
  standalone: true,
  imports: [FormsModule, ReactiveFormsModule, CommonModule],
  providers: [FeedbackService]
})
export default class FeedbackDialog implements OnInit {

  form: FormGroup = new FormGroup({
    name: new FormControl(''),
    email: new FormControl(''),
    comments: new FormControl('')
  })

  imgUrl: string;
  name = '';
  email = '';
  comments = '';

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: string,
    public dialogRef: MatDialogRef<FeedbackDialog>,
    private feedbackService: FeedbackService,
    private formBuilder: FormBuilder
  ) {
    console.log(data)
    this.imgUrl = data;
  }

  ngOnInit(): void {
    this.form = this.formBuilder.group(
      {
        name: ['', Validators.maxLength(250)],
        email: ['', [Validators.maxLength(250), Validators.email]],
        comments: ['', [Validators.minLength(10), Validators.maxLength(3000), Validators.required]]
      }
    )

  }

  get f(): { [key: string]: AbstractControl } {
    return this.form.controls;
  }

  get val(): { [key: string]: string } {
    return this.form.value;
  }

  close() {
    this.dialogRef.close();
  }

  submit() {
    console.log(this.form)
    let fb = new Feedback(this.name, this.email, this.comments);
    // this.feedbackService.post_feedback(fb).subscribe((resp) => {
    //   this.close();
    // }, (err) => {
    //   console.log(err);
    // });
    this.feedbackService.post_feedback(fb).subscribe({
      next: (resp: any) => {
        this.close();
      },
      error: (resp: any) => {
        console.log(resp);
      }
    })
  }
}